# api/services/product_service.py
"""Раздел «Товары в отгрузках»: отбор, показатели, сводка.

Живёт рядом с `material_service` и `supply_service`, а не во вью: вью остаётся
разбором параметров и конвертом ответа. Общая для списочных разделов механика —
поиск, страница, топы — в `listing`.
"""

from datetime import datetime

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.fields import DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from api.services.listing import paginate, search_q, top_n
from core.models import Product, SalesChannel, ShipmentItem


def period_bounds(start_date, end_date):
    """Границы периода как дата-время с зоной: начало первого дня и конец последнего.

    МойСклад хранит момент отгрузки со временем, поэтому «по 30 июня»
    без конца дня отрезало бы всё, что отгружено в этот день после полуночи.
    """
    since = timezone.make_aware(
        datetime.combine(start_date, datetime.min.time()),
        timezone.get_current_timezone(),
    ) if start_date else None
    until = timezone.make_aware(
        datetime.combine(end_date, datetime.max.time()),
        timezone.get_current_timezone(),
    ) if end_date else None
    return since, until


def aggregated_products(search='', subgroup='', sales_channel='', since=None, until=None):
    """Товары с показателями за период: количество, средняя цена, сумма, отгрузки.

    Общий расчёт для экрана раздела и выгрузки в Excel. Держать его в одном
    месте важнее, чем кажется: пока копии жили врозь, любое новое условие
    отбора приходилось дописывать дважды, а разъехавшись, они показали бы
    разные числа за один и тот же период — на экране одно, в файле другое.

    `since`/`until` — уже приведённые границы периода, см. `period_bounds`.
    """
    products_query = Product.objects.filter(
        group='Товары'
    ).exclude(
        subgroup__isnull=True
    )

    # Улучшенный поиск по нескольким словам
    products_query = products_query.filter(search_q(search, 'name', 'article'))

    if subgroup:
        products_query = products_query.filter(subgroup=subgroup)

    # Условия отбора отгрузок уходят прямо в агрегаты. Прежде здесь стоял
    # `filter=Q(shipmentitem__in=shipments_query)` — подзапрос по всей
    # таблице позиций, и по разу на каждый из четырёх агрегатов. Без
    # фильтров он читался как «позиция входит в множество всех позиций»:
    # не отсекал ни строки и только тратил время.
    #
    # Отсев помеченных отгрузок приходится выписывать здесь руками: он жил
    # внутри того подзапроса, потому что `ShipmentItem.objects` прячет их
    # менеджером. Обход связи (`shipmentitem__`) идёт по таблицам напрямую
    # и менеджера не спрашивает — без этой строки позиции пропавшего из
    # МойСклад документа снова попадали бы в отчёт.
    item_filter = Q(shipmentitem__shipment__deleted_at__isnull=True)
    if sales_channel:
        item_filter &= Q(shipmentitem__shipment__sales_channel__name=sales_channel)
    if since:
        item_filter &= Q(shipmentitem__shipment__date__gte=since)
    if until:
        item_filter &= Q(shipmentitem__shipment__date__lte=until)

    # Все четыре агрегата идут по одной связи, поэтому join один и суммы
    # не размножаются.
    products_data = products_query.annotate(
        total_quantity=Coalesce(
            Sum('shipmentitem__quantity', filter=item_filter),
            0,
            output_field=DecimalField()
        ),
        average_price=Coalesce(
            Avg('shipmentitem__price', filter=item_filter),
            0,
            output_field=DecimalField()
        ),
        total_sum=Coalesce(
            Sum(F('shipmentitem__quantity') * F('shipmentitem__price'),
                filter=item_filter),
            0,
            output_field=DecimalField()
        ),
        shipments_count=Count(
            'shipmentitem__shipment',
            filter=item_filter,
            distinct=True
        )
    )

    # Если выборка отгрузок сужена, товары без продаж не нужны ни на экране,
    # ни в файле.
    if since or until or sales_channel:
        products_data = products_data.filter(
            Q(total_quantity__gt=0) |
            Q(total_sum__gt=0) |
            Q(shipments_count__gt=0)
        )

    return products_query, products_data


def get_products_list(
    page=1, page_size=10, search='', subgroup='', sales_channel='',
    start_date=None, end_date=None,
    sort_field='total_quantity', sort_order='desc',
):
    """Страница раздела: строки, общее число, сводка с топами, справочники."""
    since, until = period_bounds(start_date, end_date)
    products_query, products_data = aggregated_products(
        search=search, subgroup=subgroup, sales_channel=sales_channel,
        since=since, until=until,
    )

    # Выборка позиций нужна одной цифре сводки — числу отгрузок за период.
    shipments_query = ShipmentItem.objects.all()
    if sales_channel:
        shipments_query = shipments_query.filter(
            shipment__sales_channel__name=sales_channel
        )
    if since:
        shipments_query = shipments_query.filter(shipment__date__gte=since)
    if until:
        shipments_query = shipments_query.filter(shipment__date__lte=until)

    # Топы считаем одним проходом по выборке, а не тремя запросами с той же
    # агрегацией: девять строк не стоят трёх повторов тяжёлого расчёта.
    summary = list(products_data.values(
        'name', 'total_quantity', 'total_sum', 'shipments_count'
    ))

    top_quantity_data = top_n(
        summary,
        key=lambda row: row['total_quantity'],
        build=lambda row: {
            'name': row['name'],
            'quantity': float(row['total_quantity']),
            'shipments_count': row['shipments_count']
        },
    )

    top_revenue_data = top_n(
        summary,
        key=lambda row: row['total_sum'],
        build=lambda row: {
            'name': row['name'],
            'revenue': float(row['total_sum']),
            'price_per_unit': float(
                row['total_sum'] / row['total_quantity'] if row['total_quantity'] else 0
            )
        },
    )

    # Среднее считаем только по тем, у кого были отгрузки: иначе деление
    # на ноль, да и «в среднем за отгрузку» без отгрузок ничего не значит.
    top_average_data = top_n(
        [row for row in summary if row['shipments_count'] > 0],
        key=lambda row: float(row['total_quantity']) / row['shipments_count'],
        build=lambda row: {
            'name': row['name'],
            'average_quantity': '%.1f шт. в среднем за отгрузку' % (
                float(row['total_quantity']) / row['shipments_count']
            )
        },
    )

    # Статистика
    stats = {
        'total_products': len(summary),
        'total_shipments': shipments_query.values('shipment').distinct().count(),
        'top_by_quantity': top_quantity_data,
        'top_by_revenue': top_revenue_data,
        'top_by_average_quantity': top_average_data
    }

    # Применяем сортировку. Последним ключом всегда идентификатор: товары
    # с одинаковой суммой иначе переставляются между страницами, и при
    # листании один показался бы дважды, а другой пропал.
    sort_mapping = {
        'name': 'name',
        'subgroup': 'subgroup',
        'quantity': 'total_quantity',
        'total_quantity': 'total_quantity',
        'average_price': 'average_price',
        'total_sum': 'total_sum',
        'shipments_count': 'shipments_count'
    }
    if sort_field in sort_mapping:
        sort_prefix = '-' if sort_order == 'desc' else ''
        products_data = products_data.order_by(
            f'{sort_prefix}{sort_mapping[sort_field]}', 'pk'
        )

    # Пагинация
    page_data, total = paginate(products_data, page, page_size)

    # Форматируем данные для ответа
    products_list = []
    for product in page_data:
        products_list.append({
            'id': product.id,
            'name': product.name,
            'group': product.group,
            'subgroup': product.subgroup,
            'quantity': float(product.total_quantity),
            'average_price': float(product.average_price),
            'total_sum': float(product.total_sum),
            'shipments_count': product.shipments_count
        })

    # Справочники здесь считаются по текущему отбору, а не по всему
    # каталогу, — этим и отличаются от `get_product_filters`, которая
    # наполняет панель фильтров.
    return {
        'products': products_list,
        'total': total,
        'stats': stats,
        'available_subgroups': list(products_query.values_list(
            'subgroup', flat=True
        ).distinct().order_by('subgroup')),
        # Только каналы, по которым что-то отгружалось: справочник
        # МойСклада содержит и заведённые впрок, а выбор такого означал бы
        # заведомо пустую таблицу.
        'available_sales_channels': list(
            SalesChannel.objects.filter(shipments__isnull=False,
                                        shipments__deleted_at__isnull=True)
            .values_list('name', flat=True)
            .distinct()
        ),
    }


def get_product_filters():
    """Справочники для панели фильтров: подгруппы и каналы продаж.

    Отдельно от расчёта: панели нужны два списка строк, а не агрегация по
    отгрузкам. Раньше она брала их из общего ответа, и открытие раздела
    дважды запускало полный пересчёт.
    """
    subgroups = Product.objects.filter(
        group='Товары'
    ).exclude(
        subgroup__isnull=True
    ).values_list('subgroup', flat=True).distinct().order_by('subgroup')

    # Только каналы, по которым что-то отгружалось: справочник МойСклада
    # содержит и заведённые впрок, а выбор такого означал бы заведомо
    # пустую таблицу.
    channels = SalesChannel.objects.filter(
        shipments__isnull=False, shipments__deleted_at__isnull=True
    ).values_list('name', flat=True).distinct()

    return {
        'available_subgroups': list(subgroups),
        'available_sales_channels': list(channels),
    }
