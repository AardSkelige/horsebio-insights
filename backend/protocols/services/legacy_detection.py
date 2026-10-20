import re
from pathlib import Path

PROTOCOL_TEMPLATE_META = {
    "hondrofit_mixed_dogs_horses": {
        "title": "Хондрофит ArtroPro для собак и лошадей (объединённый)",
        "path": "Собаки/Жидкое на воде/Техпротокол Хондропротектор Хондрофит ArtroPro для собак.docx",
    },
    "hondrofit_plus_mixed_dogs_horses": {
        "title": "Хондрофит ПЛЮС ArtroPro для собак и лошадей (объединённый)",
        "path": "Собаки/Жидкое на воде/Техпротокол Хондропротектор Хондрофит ПЛЮС ArtroPro для собак.docx",
    },
    "hondrofit_plus_dogs": {
        "title": "Хондрофит ПЛЮС ArtroPro для собак",
        "path": "Собаки/Жидкое на воде/Техпротокол Хондропротектор Хондрофит ПЛЮС ArtroPro для собак.docx",
    },
    "flexinil_extra_devils_claw_mixed_dogs_horses": {
        "title": "Флексинил Экстра для собак и Дьявольский коготь для лошадей (объединённый)",
        "path": "Собаки и лошади/Жидкое на масле/Техпротокол Флексинил Экстра для собак и Дьявольский коготь для лошадей.docx",
    },
    "quietpro_mixed_dogs_horses": {
        "title": "Успокоительный эликсир QuietPro для собак и лошадей (объединённый)",
        "path": "Собаки и лошади/Жидкое на масле/Техпротокол Успокоительный эликсир QuietPro для собак и лошадей на основе льняного масла.docx",
    },
    "psyllium_mixed_dogs_horses": {
        "title": "Псиллиум GastroPro для собак, кошек и лошадей (объединённый)",
        "path": "Собаки и лошади/Порошки/Техпротокол Псиллиум GastroPro для собак, кошек и лошадей.docx",
    },
    "chamomile_mixed_dogs_horses": {
        "title": "Ромашка GastroPro для собак и лошадей на основе льняного масла (объединённый)",
        "path": "Собаки и лошади/Жидкое на масле/Техпротокол Ромашка GastroPro для собак и лошадей на основе льняного масла.docx",
    },
    "devils_claw_horse_linseed_oil": {
        "title": "Дьявольский коготь ArtroPro для лошадей на основе льняного масла",
        "path": "Лошади/Жидкое на масле/Техпротокол Дьявольский коготь с вит С ArtroPro для лошадей на воде.docx",
    },
    "devils_claw_horse_water": {
        "title": "Дьявольский коготь ArtroPro для лошадей с витамином С на водной основе",
        "path": "Лошади/Жидкое/Техпротокол Дьявольский коготь с вит С ArtroPro для лошадей на воде.docx",
    }
}


def norm_text(x):
    x = str(x or "").lower().replace("ё", "е")
    x = re.sub(r"[^а-яa-z0-9]+", " ", x)
    return re.sub(r"\s+", " ", x).strip()


def protocol_templates(folder):
    out = dict(PROTOCOL_TEMPLATE_META)
    folder = Path(folder)
    for path in sorted(folder.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        rel = path.relative_to(folder)
        raw_key = "__".join(rel.with_suffix("").parts)
        key_base = re.sub(r"[^0-9A-Za-zА-Яа-я_]+", "_", raw_key).strip("_") or path.stem
        key = key_base
        suffix = 2
        while key in out:
            key = f"{key_base}_{suffix}"
            suffix += 1
        out.setdefault(key, {"title": path.stem.replace("_", " "), "path": rel.as_posix()})
    return out


def protocol_detect_template(parsed, templates):
    if not templates:
        return "", 0

    sources = [row.get("source_name") or "" for row in parsed.get("products") or []]
    source_text = " ".join(sources)
    if not source_text.strip():
        return "", 0
    source_tokens = set(protocol_template_norm(source_text).split())
    product_kind = protocol_template_kind(source_text)
    product_kinds = {
        protocol_template_kind(source)
        for source in sources
    }
    product_kinds.discard("")
    product_animals = set()
    for source in sources:
        source_norm = protocol_match_norm(source)
        if "лошад" in source_norm:
            product_animals.add("horse")
        if "собак" in source_norm or "кош" in source_norm:
            product_animals.add("dog")
    if product_kinds == {"flexinil_extra", "devils_claw"} and product_animals == {"dog", "horse"}:
        mixed_key = "flexinil_extra_devils_claw_mixed_dogs_horses"
        if mixed_key in templates:
            return mixed_key, 4.0
    if (
        product_animals == {"dog", "horse"}
        and product_kinds == {"gastro"}
        and all("ромашка" in protocol_match_norm(source) for source in sources)
    ):
        mixed_key = "chamomile_mixed_dogs_horses"
        if mixed_key in templates:
            return mixed_key, 4.0
    if product_animals == {"dog", "horse"}:
        mixed_key = {
            "hondrofit": "hondrofit_mixed_dogs_horses",
            "hondrofit_plus": "hondrofit_plus_mixed_dogs_horses",
            "quiet": "quietpro_mixed_dogs_horses",
            "psyllium": "psyllium_mixed_dogs_horses",
        }.get(product_kind)
        if mixed_key and mixed_key in templates:
            return mixed_key, 4.0
    if (
        product_kinds == {"hondrofit_plus"}
        and product_animals == {"dog"}
        and "hondrofit_plus_dogs" in templates
    ):
        return "hondrofit_plus_dogs", 4.0
    source_norm = protocol_match_norm(source_text)
    if (
        product_kinds == {"devils_claw"}
        and product_animals == {"horse"}
        and ("водн" in source_norm or "на воде" in source_norm)
        and "devils_claw_horse_water" in templates
    ):
        return "devils_claw_horse_water", 4.0
    if (
        product_kinds == {"devils_claw"}
        and product_animals == {"horse"}
        and "льнян" in source_norm
        and "масл" in source_norm
        and "devils_claw_horse_linseed_oil" in templates
    ):
        return "devils_claw_horse_linseed_oil", 4.0
    product_animal = protocol_template_animal(source_text)
    product_form = protocol_template_form(source_text)
    ranked = []
    for key, data in templates.items():
        if key in {
            "hondrofit_mixed_dogs_horses",
            "hondrofit_plus_mixed_dogs_horses",
            "hondrofit_plus_dogs",
            "flexinil_extra_devils_claw_mixed_dogs_horses",
            "quietpro_mixed_dogs_horses",
            "psyllium_mixed_dogs_horses",
            "chamomile_mixed_dogs_horses",
            "devils_claw_horse_linseed_oil",
            "devils_claw_horse_water",
        }:
            continue
        title = data.get("title") or key
        filename = data.get("path") or key
        folder_hint = " ".join(Path(filename).with_suffix("").parts)
        candidate_kind = protocol_template_kind(folder_hint)
        candidate_animal = protocol_template_animal(folder_hint)
        candidate_form = protocol_template_form(folder_hint)
        if product_kind and candidate_kind != product_kind:
            continue
        if product_animal and candidate_animal != product_animal:
            continue
        if product_form and candidate_form != product_form:
            continue
        candidate_tokens = set(protocol_template_norm(folder_hint).split())
        overlap = len(source_tokens & candidate_tokens) / max(1, len(candidate_tokens))
        structured = sum(bool(value) for value in (product_kind, product_animal, product_form))
        ranked.append((structured + overlap, key))

    if not ranked:
        return "", 0
    ranked.sort(reverse=True)
    best_score, best_key = ranked[0]
    if len(ranked) > 1 and abs(best_score - ranked[1][0]) < 0.05:
        return "", 0
    return best_key, best_score


def protocol_best_template_name(source_name, template_names, item=None):
    aliases = [source_name]
    if item:
        aliases.append(item["name"])
        aliases.extend(x.strip() for x in str(item["synonyms"] or "").split(",") if x.strip())
    alias_norms = {protocol_match_norm(alias) for alias in aliases if alias}
    alias_keys = {protocol_exact_key(alias) for alias in aliases if alias}
    matches = [
        name for name in template_names
        if protocol_match_norm(name) in alias_norms or protocol_exact_key(name) in alias_keys
    ]
    if len(matches) == 1:
        return matches[0]
    if matches:
        return ""

    alias_token_sets = [
        set(protocol_match_norm(alias).split())
        for alias in aliases
        if alias
    ]
    ranked = []
    for name in template_names:
        template_tokens = set(protocol_match_norm(name).split())
        best_score = None
        for alias_tokens in alias_token_sets:
            common = alias_tokens & template_tokens
            if len(common) < 3:
                continue
            coverage = len(common) / max(1, min(len(alias_tokens), len(template_tokens)))
            jaccard = len(common) / max(1, len(alias_tokens | template_tokens))
            if coverage < 0.9:
                continue
            score = (coverage, jaccard, len(common))
            if best_score is None or score > best_score:
                best_score = score
        if best_score is not None:
            ranked.append((best_score, name))
    ranked.sort(reverse=True)
    if not ranked:
        return ""
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return ""
    return ranked[0][1]


def protocol_match_norm(value):
    text = norm_text(value)
    return text.translate(str.maketrans({"c": "с", "a": "а", "e": "е", "o": "о", "p": "р", "x": "х", "y": "у"}))


def protocol_exact_key(value):
    return " ".join(sorted(protocol_match_norm(value).split()))


def protocol_template_norm(value):
    text = protocol_match_norm(value)
    text = re.sub(r"\bтехпротокол\b", " ", text)
    text = re.sub(r"\bнаклейк\w*\b|\bэтикетк\w*\b", " ", text)
    text = re.sub(r"\bуп\b|\bшт\b|\bмг\b|\bг\b|\bмл\b", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    stop_words = (
        "для", "на", "основе", "с", "со", "и", "всех", "возрастов",
        "пород", "крупных", "мелких", "средних", "кошек", "собак", "лошадей",
        "чувствительным", "пищеварением", "помпой", "дозатором", "банка",
        "капсулы", "желатиновые", "жидкое", "масле", "воде", "порошки",
    )
    for word in stop_words:
        text = re.sub(rf"\b{re.escape(word)}\b", " ", text)
    return " ".join(text.split())


def protocol_template_kind(value):
    text = protocol_match_norm(value)
    checks = [
        ("hondrofit_plus", ("хондрофит плюс",)),
        ("hondrofit", ("хондрофит",)),
        ("hondro_light", ("хондро лайт",)),
        ("hondro", ("хондро ", "хондропротектор хондро")),
        ("flexinil_extra", ("флексинил экстра",)),
        ("flexinil_plus", ("флексинил плюс",)),
        ("flexinil", ("флексинил",)),
        ("beef_collagen", ("говяжий коллаген",)),
        ("fish_collagen", ("рыбный коллаген",)),
        ("msm", ("мсм",)),
        ("multicalcium", ("мультикальций",)),
        ("biotin", ("биотин",)),
        ("vitamin_c", ("витамин с",)),
        ("junior", ("джуниор",)),
        ("psyllium", ("псиллиум",)),
        ("florinorm", ("флоринорм",)),
        ("electrolyte", ("электролит",)),
        ("equibase", ("эквибаза",)),
        ("devils_claw", ("дьявольский коготь",)),
        ("vitamin_e_plus", ("витамин е плюс",)),
        ("vitamin_e", ("витамин е",)),
        ("linseed_oil", ("льняное масло",)),
        ("broncho", ("легочный эликсир", "bronchopro")),
        ("immuno", ("общеукрепляющий эликсир", "immunopro", "чеснок", "эхинацея")),
        ("quiet", ("успокоительный эликсир", "quietpro")),
        ("gastro", ("ромашка", "gastropro", "эквигард", "пробиотик")),
        ("masspro", ("мускул", "masspro")),
        ("hoof", ("подкормка для копыт",)),
        ("cream", ("антибактерин", "декалар", "юнифлекс")),
    ]
    for key, tokens in checks:
        if any(token in text for token in tokens):
            return key
    return ""


def protocol_template_animal(value):
    text = protocol_match_norm(value)
    if "лошад" in text:
        return "horse"
    if "собак" in text or "кош" in text:
        return "dog"
    return ""


def protocol_template_form(value):
    text = protocol_match_norm(value)
    if "капсул" in text:
        return "capsule"
    if "крем" in text or "гель" in text:
        return "cream"
    if "жидкое" in text or "эликсир" in text or "мл" in text or "водн" in text or "масл" in text:
        return "liquid"
    if "порош" in text or re.search(r"\b\d+\s*г\b", str(value or "").lower()):
        return "powder"
    return ""
