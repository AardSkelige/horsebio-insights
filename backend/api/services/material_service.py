# api/services/material_service.py
"""Раздел «Материалы в отгрузках»: отбор, показатели, сводка.

Живёт рядом с `supply_service`, а не во вью: вью остаётся разбором параметров
и конвертом ответа, как и положено REST-слою. Общая для всех списочных
разделов механика — поиск и страница — в `listing`.
"""

from django.db.models import Count, Sum
from django.utils.dateparse import parse_date

from api.services.listing import paginate, search_q
from core.models import Counterparty, RawMaterial, RawMaterialUsage, SupplyItem

# Группы материалов, с которыми работают оба раздела — «Материалы
# в отгрузках» и «Материалы в поставках». Список один на двоих: дописать
# четвёртую группу в одном месте и забыть про второе значило бы, что разделы
# начнут отбирать разное.
VALID_GROUPS = [
    'Тара',
    'Материалы для производства',
    'Этикетки'
]


class _Reversed:
    """Обратный порядок для одного текстового ключа сортировки.

    Число для убывания достаточно взять со знаком минус, строку — нет.
    А перевернуть весь список нельзя: направление касается только своей
    колонки, приоритет группы и точное совпадение остаются сверху.
    """

    __slots__ = ('value',)

    def __init__(self, value):
        self.value = value

    def __lt__(self, other):
        return other.value < self.value

    def __eq__(self, other):
        return other.value == self.value


def get_materials_list(
    page=1, page_size=10, search='', group='',
    start_date=None, end_date=None, counterparties=None,
    sort_field='name', sort_order='asc',
):
    """Страница раздела: строки, общее число, сводка по группам, поставщики."""
    counterparties = counterparties or []

    # Базовый QuerySet для материалов
    materials_query = RawMaterial.objects.filter(group__in=VALID_GROUPS)

    # Промежуточный QuerySet для отслеживания фильтрации
    filtered_materials = materials_query

    # Фильтр по поиску (case-insensitive)
    filtered_materials = filtered_materials.filter(
        search_q(search, 'name', 'code', 'article')
    )

    # Фильтр по группе
    if group:
        filtered_materials = filtered_materials.filter(group=group)

    # Фильтр по контрагентам
    if counterparties:
        materials_supplied = RawMaterial.objects.filter(
            supplyitem__supply__counterparty__id__in=counterparties
        ).distinct()
        filtered_materials = filtered_materials.filter(id__in=materials_supplied.values_list('id', flat=True))

    # Показатели считаем двумя группировками, по одной на связь.
    #
    # Обойти материалы циклом нельзя — это запрос на строку. Но и вешать
    # подзапрос на каждый показатель нельзя тоже: подзапрос коррелирован,
    # то есть выполняется заново для каждого материала и каждый раз
    # повторяет join к отгрузкам. Замер на проде: одна плоская
    # группировка по всей таблице расхода — 1 с, те же числа
    # подзапросами — 96 с.
    #
    # Одной аннотацией показатели не собрать: расход и поставки — разные
    # связи, join по обеим размножил бы строки, и суммы бы перемножились.
    # Поэтому две группировки, а склейка и сортировка — здесь, в Python:
    # материалов сотни, это бесплатно.
    parsed_start_date = parse_date(start_date) if start_date else None
    parsed_end_date = parse_date(end_date) if end_date else None

    rows = list(filtered_materials.values('id', 'name', 'code', 'group', 'uom_name'))
    material_ids = [row['id'] for row in rows]

    usage_query = RawMaterialUsage.objects.filter(raw_material_id__in=material_ids)
    if parsed_start_date:
        usage_query = usage_query.filter(shipment_item__shipment__date__gte=parsed_start_date)
    if parsed_end_date:
        usage_query = usage_query.filter(shipment_item__shipment__date__lte=parsed_end_date)

    usage_by_material = {
        row['raw_material']: row
        for row in usage_query.values('raw_material').annotate(
            quantity=Sum('quantity'),
            shipments=Count('shipment_item__shipment', distinct=True),
        )
    }

    supply_items_query = SupplyItem.objects.filter(raw_material_id__in=material_ids)
    if counterparties:
        supply_items_query = supply_items_query.filter(
            supply__counterparty__id__in=counterparties
        )
    if parsed_start_date:
        supply_items_query = supply_items_query.filter(supply__date__gte=parsed_start_date)
    if parsed_end_date:
        supply_items_query = supply_items_query.filter(supply__date__lte=parsed_end_date)

    supplies_by_material = {
        row['raw_material']: row
        for row in supply_items_query.values('raw_material').annotate(
            quantity=Sum('quantity'),
            suppliers=Count('supply__counterparty', distinct=True),
        )
    }

    # Когда выборка сужена поставками, в колонке показываем поставленное,
    # иначе израсходованное.
    narrowed = bool(counterparties or start_date or end_date)

    materials_data = []
    for row in rows:
        usage = usage_by_material.get(row['id'])
        supply = supplies_by_material.get(row['id'])
        supplied_quantity = supply['quantity'] if supply else None
        used_quantity = usage['quantity'] if usage else None
        total_quantity = supplied_quantity if narrowed else used_quantity

        materials_data.append({
            'id': row['id'],
            'name': row['name'],
            'code': row['code'] or '-',
            'group': row['group'],
            'uom': row['uom_name'],
            'total_usage': float(total_quantity or 0),
            'shipments_count': usage['shipments'] if usage else 0,
            'suppliers_count': supply['suppliers'] if supply else 0,
        })

    # Сортировка данных
    # Priority for groups: production materials first, then containers, then labels
    GROUP_PRIORITY = {
        'Материалы для производства': 0,
        'Тара': 1,
        'Этикетки': 2
    }
    NUMERIC_SORT = {'total_usage', 'shipments_count', 'suppliers_count'}
    TEXT_SORT = {'name', 'code', 'group', 'uom'}
    descending = sort_order == 'desc'
    needle = search.lower().strip()

    def sort_key(item):
        # Точное совпадение с поиском идёт первым, затем приоритет группы,
        # затем сама колонка. Идентификатор последним ключом: без него
        # строки с одинаковыми значениями переставляются между страницами,
        # и при листании один материал показался бы дважды, а другой
        # пропал.
        is_exact = bool(needle) and item['name'].lower().strip() == needle
        head = (not is_exact, GROUP_PRIORITY.get(item['group'], 99))

        if sort_field in NUMERIC_SORT:
            value = float(item[sort_field] or 0)
            return head + (-value if descending else value, item['id'])
        if sort_field in TEXT_SORT:
            value = (item[sort_field] or '').lower()
            return head + (_Reversed(value) if descending else value, item['id'])
        return head + (item['id'],)

    materials_data.sort(key=sort_key)

    # Пагинация результатов
    page_data, total = paginate(materials_data, page, page_size)

    # Статистика с учетом всех фильтров
    stats = {
        'Материалы для производства': 0,
        'Тара': 0,
        'Этикетки': 0,
    }
    for item in materials_data:
        if item['group'] in stats:
            stats[item['group']] += 1

    # Получаем список контрагентов только для отфильтрованных материалов
    counterparties_list = Counterparty.objects.filter(
        supply__items__raw_material_id__in=material_ids
    ).distinct().values('id', 'name').order_by('name')

    return {
        'materials': list(page_data),
        'total': total,
        'stats': stats,
        'available_groups': VALID_GROUPS,
        'counterparties': list(counterparties_list),
    }


def get_material_filters():
    """Справочники для панели фильтров: группы и поставщики.

    Отдельно от расчёта: панели нужны два списка, а не показатели. Раньше она
    брала их из общего ответа, и открытие раздела дважды запускало подсчёт
    расхода и поставок — второй раз ради выпадающих списков.
    """
    counterparties = Counterparty.objects.filter(
        supply__items__raw_material__group__in=VALID_GROUPS
    ).distinct().values('id', 'name').order_by('name')

    return {
        'available_groups': VALID_GROUPS,
        'counterparties': list(counterparties),
    }
