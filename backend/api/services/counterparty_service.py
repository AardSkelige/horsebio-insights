# api/services/counterparty_service.py
"""Раздел «Контрагенты»: отбор, показатели, сводка.

Живёт рядом с остальными сервисами разделов, а не во вью: вью остаётся
разбором параметров и конвертом ответа. Общая механика списков — поиск
и страница — в `listing`.
"""

from datetime import datetime

from django.db.models import Count, F, Max, Q, Sum
from django.db.models.fields import DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone

from api.services.listing import paginate, search_q
from core.models import Counterparty, Shipment, ShipmentItem


def get_counterparties_list(
    page=1, page_size=10, search='',
    start_date=None, end_date=None,
    sort_field='total_sales', sort_order='desc',
):
    """Страница раздела: строки, общее число и сводка."""

    # Базовый QuerySet для отгрузок с фильтрацией по датам
    shipments_query = Shipment.objects.all()
    
    if start_date:
        start_date = timezone.make_aware(
            datetime.combine(start_date, datetime.min.time()),
            timezone.get_current_timezone(),
        )
        shipments_query = shipments_query.filter(date__gte=start_date)

    if end_date:
        end_date = timezone.make_aware(
            datetime.combine(end_date, datetime.max.time()),
            timezone.get_current_timezone(),
        )
        shipments_query = shipments_query.filter(date__lte=end_date)

    # Получаем ID контрагентов с отгрузками за период
    counterparty_ids = shipments_query.values_list('counterparty_id', flat=True).distinct()

    # Условия отбора отгрузок — прямо в агрегаты. Раньше здесь стоял
    # `filter=Q(shipment__in=shipments_query)`: подзапрос по всей таблице
    # отгрузок, и по разу на каждый из четырёх агрегатов.
    #
    # Отсев помеченных отгрузок выписан руками: он приезжал внутри того
    # подзапроса вместе с менеджером `Shipment.objects`, а обход связи
    # (`shipment__`) идёт по таблицам напрямую и менеджера не спрашивает.
    shipment_filter = Q(shipment__deleted_at__isnull=True)
    if start_date:
        shipment_filter &= Q(shipment__date__gte=start_date)
    if end_date:
        shipment_filter &= Q(shipment__date__lte=end_date)

    # Базовый QuerySet для контрагентов
    counterparties_query = Counterparty.objects.filter(id__in=counterparty_ids).annotate(
        shipments_count=Count(
            'shipment',
            filter=shipment_filter,
            distinct=True
        ),
        total_sales=Coalesce(
            Sum(
                F('shipment__items__quantity') * F('shipment__items__price'),
                filter=shipment_filter,
                output_field=DecimalField()
            ),
            0,
            output_field=DecimalField()
        ),
        total_products=Count(
            'shipment__items__product',
            filter=shipment_filter,
            distinct=True
        ),
        last_shipment=Max('shipment__date', filter=shipment_filter)
    )

    # Улучшенный поиск по нескольким словам
    counterparties_query = counterparties_query.filter(search_q(search, 'name'))

    # Получаем отфильтрованные отгрузки для найденных контрагентов
    filtered_shipments = shipments_query.filter(
        # `values('pk')` — чтобы в подзапрос не уехали четыре агрегата:
        # для отбора нужны только идентификаторы.
        counterparty__in=counterparties_query.values('pk')
    )

    # Получаем отфильтрованные товары
    filtered_items = ShipmentItem.objects.filter(
        shipment__in=filtered_shipments
    )

    # Применяем сортировку. Последним ключом идентификатор: контрагенты
    # с одинаковым значением иначе переставляются между страницами, и при
    # листании один показался бы дважды, а другой пропал.
    if sort_field in ('name', 'total_sales', 'shipments_count', 'total_products', 'last_shipment'):
        sort_prefix = '-' if sort_order == 'desc' else ''
        counterparties_query = counterparties_query.order_by(
            f'{sort_prefix}{sort_field}', 'pk'
        )

    # Пагинация
    page_data, total = paginate(counterparties_query, page, page_size)

    # Число контрагентов берём у пагинатора: он уже посчитал его тем же
    # запросом. Отдельный `count()` по выборке с четырьмя агрегатами стоил
    # ровно столько же и выполнялся на каждый показ страницы вторым разом.
    stats = {
        'total_counterparties': total,
        'total_shipments': filtered_shipments.count(),
        'total_products': filtered_items.values('product').distinct().count()
    }

    # Форматируем данные для ответа
    counterparties_data = []
    for c in page_data:
        counterparty_data = {
            'id': c.id,
            'name': c.name,
            'total_sales': float(c.total_sales),
            'shipments_count': c.shipments_count,
            'total_products': c.total_products,
            'last_shipment': c.last_shipment.isoformat() if c.last_shipment else None
        }
        counterparties_data.append(counterparty_data)

    return {
        'counterparties': counterparties_data,
        'total': total,
        'stats': stats,
    }
