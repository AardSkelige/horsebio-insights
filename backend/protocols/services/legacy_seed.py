import re
import sqlite3
from datetime import datetime
from pathlib import Path

from django.db import transaction

from core.models import ProcessingPlan, RawMaterial
from protocols.models import ManualSeries, ProtocolTemplate, TemplateLink, TemplateMaterial
from protocols.services import legacy_detection as legacy
from protocols.services.render import template_rows

MIN_SCORE = 0.35
MERGES = [
    ('hondrofit_mixed_dogs_horses', lambda name: legacy.protocol_template_kind(name) == 'hondrofit'),
    ('hondrofit_plus_mixed_dogs_horses', lambda name: legacy.protocol_template_kind(name) == 'hondrofit_plus'),
    ('quietpro_mixed_dogs_horses', lambda name: legacy.protocol_template_kind(name) == 'quiet'),
    ('psyllium_mixed_dogs_horses', lambda name: legacy.protocol_template_kind(name) == 'psyllium'),
    ('chamomile_mixed_dogs_horses', lambda name: 'ромашка' in legacy.protocol_match_norm(name)),
    ('flexinil_extra_devils_claw_mixed_dogs_horses', lambda name: (
        legacy.protocol_template_kind(name) == 'flexinil_extra'
        or (legacy.protocol_template_kind(name) == 'devils_claw' and 'масл' in legacy.protocol_match_norm(name))
    )),
]


def _site_items(db_path):
    connection = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        items = connection.execute("SELECT name, synonyms FROM items WHERE category = 'сырьё'").fetchall()
        production = connection.execute(
            'SELECT name, synonyms, manufacturer, series, expiry_date FROM production_nomenclature WHERE is_active = 1'
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in items], [dict(row) for row in production]


def _title(stem):
    return ' '.join(re.sub(r'^\s*техпротокол\s+', '', stem, flags=re.I).split())


def _load_templates(folder):
    keys = legacy.protocol_templates(folder)
    by_path = {}
    for path in sorted(Path(folder).rglob('*.docx')):
        if path.name.startswith('~$'):
            continue
        relative = path.relative_to(folder).as_posix()
        by_path[relative], _ = ProtocolTemplate.objects.update_or_create(
            file_name=relative, defaults={'title': _title(path.stem), 'content': path.read_bytes()},
        )
    return keys, {key: by_path[data['path']] for key, data in keys.items() if data['path'] in by_path}


def _same_kind(plan_name, template_path):
    return legacy.protocol_template_kind(plan_name) == legacy.protocol_template_kind(template_path)


def _link_plans(keys, templates):
    unlinked = []
    for plan in ProcessingPlan.objects.prefetch_related('products__product'):
        products = [{'source_name': p.product.name} for p in plan.products.all()]
        key, score = legacy.protocol_detect_template({'products': products}, keys)
        template = templates.get(key) if score >= MIN_SCORE and _same_kind(plan.name, keys[key]['path']) else None
        if template is None:
            unlinked.append(plan.name)
            continue
        TemplateLink.objects.update_or_create(
            plan_external_id=plan.external_id, defaults={'plan_name': plan.name, 'template': template},
        )
    return unlinked


def _merge(templates):
    for key, belongs in MERGES:
        target = templates.get(key)
        if target is None:
            continue
        members = {link.template for link in TemplateLink.objects.select_related('template') if belongs(link.plan_name)}
        for template in members - {target}:
            template.merge_into = target
            template.save(update_fields=['merge_into'])


def _item_for(material, items):
    key = legacy.protocol_exact_key(material.name)
    return next((i for i in items if legacy.protocol_exact_key(i['name']) == key), None)


def _map_materials(items):
    plan_materials = {}
    for plan in ProcessingPlan.objects.prefetch_related('materials__material'):
        plan_materials[plan.external_id] = [m.material for m in plan.materials.all()]

    unmapped = 0
    for template in ProtocolTemplate.objects.all():
        rows = template_rows(template)
        plans = TemplateLink.objects.filter(template__in=[template, *template.merged_from.all()])
        candidates = {m for link in plans for m in plan_materials.get(link.plan_external_id, [])}
        claimed = set()
        for material in sorted(candidates, key=lambda m: m.name):
            row = legacy.protocol_best_template_name(material.name, rows, item=_item_for(material, items))
            if row and row not in claimed:
                claimed.add(row)
                TemplateMaterial.objects.update_or_create(template=template, row_name=row, defaults={'material': material})
        unmapped += len(set(rows) - claimed)
    return unmapped


def _manual_series(production):
    materials = {legacy.protocol_exact_key(m.name): m for m in RawMaterial.objects.all()}
    saved = 0
    for row in production:
        material = materials.get(legacy.protocol_exact_key(row['name']))
        if material is None or not (row['series'] or row['expiry_date'] or row['manufacturer']):
            continue
        try:
            expiry = datetime.fromisoformat(str(row['expiry_date'] or '').strip()).date()
        except ValueError:
            expiry = None
        ManualSeries.objects.update_or_create(material=material, defaults={
            'series': (row['series'] or '').strip(),
            'expiry_date': expiry,
            'manufacturer': (row['manufacturer'] or '').strip(),
        })
        saved += 1
    return saved


@transaction.atomic
def seed(templates_folder, db_path):
    items, production = _site_items(db_path)
    keys, templates = _load_templates(templates_folder)
    unlinked = _link_plans(keys, templates)
    _merge(templates)
    return {
        'templates': ProtocolTemplate.objects.count(),
        'linked': TemplateLink.objects.count(),
        'unlinked': unlinked,
        'unmapped_rows': _map_materials(items + production),
        'manual_series': _manual_series(production),
    }
