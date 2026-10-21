import math
import statistics
from collections import defaultdict
from datetime import date

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from api.services import fbo_stock
from core.models import ShipmentItem
from production_plan.models import Exclusion, GreenItem, OzonMonthSales, WbOrder
from production_plan.services import wb_sales
from production_plan.services.articles import normalize

MONTHS = 3
RESERVE_MONTHS = 2
DAYS_IN_MONTH = 30
SPIKE_RATIO = 2
SPIKE_MIN = 20

# Ozon ФАРМ берём из API, его отгрузки в МойСклад не считаем, иначе продажа посчитается дважды
OZON = 'Озон'
OZON_IP = 'Озон (ИП'
WB = 'Вб Вайлдберриз'
CHANNELS = [
    ('ozon', 'Ozon'),
    ('wb', 'WB'),
    ('wb_shipped', 'WB · отгружено нами'),
    ('yandex', 'Яндекс · отгружено нами'),
    ('ozon_ip', 'Ozon ИП'),
    ('direct', 'Дилеры, сайт, чаты'),
]
STATUS_ORDER = ['urgent', 'produce', 'in_production', 'enough']


def full_months(today, count=MONTHS):
    year, month = today.year, today.month
    result = []
    for _ in range(count):
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
        result.append(date(year, month, 1))
    return result[::-1]


def channel(counterparty):
    if counterparty == WB:
        return 'wb_shipped'
    if counterparty.startswith('Яндекс Маркет'):
        return 'yandex'
    if counterparty.startswith(OZON_IP):
        return 'ozon_ip'
    return 'direct'


def excluded(article, name, rules):
    lowered = name.lower()
    return any(normalize(rule) == article or rule.lower() in lowered for rule in rules)


def build(months, sales, stock, rules, green):
    rows = []
    for item in stock:
        article = normalize(item['article'])
        if not article or excluded(article, item['name'], rules):
            continue
        by_channel = sales.get(article, {})
        per_month = [sum(by_channel.get(key, {}).get(month, 0) for key, _ in CHANNELS) for month in months]
        if not any(per_month):
            continue
        usual = statistics.median(per_month)
        available = max(item['quantity'], 0)
        in_production = max(item['in_transit'], 0)
        need = math.ceil(usual * RESERVE_MONTHS)
        produce = max(math.ceil(need - available - in_production), 0)
        days = math.floor(available / usual * DAYS_IN_MONTH) if usual else None
        if produce and days < DAYS_IN_MONTH:
            status = 'urgent'
        elif produce:
            status = 'produce'
        elif in_production and need > available:
            status = 'in_production'
        else:
            status = 'enough'
        rows.append({
            'article': item['article'],
            'name': item['name'],
            'months': per_month,
            'spikes': [i for i, value in enumerate(per_month) if usual and value >= usual * SPIKE_RATIO and value - usual >= SPIKE_MIN],
            'channels': [
                {'key': key, 'label': label, 'months': [by_channel[key].get(month, 0) for month in months]}
                for key, label in CHANNELS if key in by_channel
            ],
            'usual': usual,
            'need': need,
            'days': days,
            'available': available,
            'in_production': in_production,
            'produce': produce,
            'status': status,
            'green': article in green,
        })
    rows.sort(key=lambda row: (STATUS_ORDER.index(row['status']), row['days'] if row['days'] is not None else math.inf, -row['produce'], row['name']))
    return rows


def wb_months(months):
    loaded = wb_sales.state()
    if loaded is None:
        return []
    until = timezone.localdate(loaded.synced_at)
    return [month for month in months if month >= loaded.covered_from and _next_month(month) <= until]


def collect_sales(months):
    sales = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for row in OzonMonthSales.objects.filter(month__in=months):
        sales[row.article]['ozon'][row.month] += row.quantity
    from_wb = wb_months(months)
    if from_wb:
        ordered = (
            WbOrder.objects
            .filter(date__date__gte=from_wb[0], date__date__lt=_next_month(from_wb[-1]), is_cancel=False)
            .annotate(month=TruncMonth('date')).values('article', 'month').annotate(quantity=Count('id'))
        )
        for row in ordered:
            sales[row['article']]['wb'][row['month'].date()] += row['quantity']
    shipped = (
        ShipmentItem.objects
        .filter(shipment__date__date__gte=months[0], shipment__date__date__lt=_next_month(months[-1]))
        .exclude(Q(shipment__counterparty__name__startswith=OZON) & ~Q(shipment__counterparty__name__startswith=OZON_IP))
        .annotate(month=TruncMonth('shipment__date'))
        .values('product__article', 'shipment__counterparty__name', 'month')
        .annotate(quantity=Sum('quantity'))
    )
    for row in shipped:
        article = normalize(row['product__article'])
        key = channel(row['shipment__counterparty__name'])
        month = row['month'].date()
        if article and not (key == 'wb_shipped' and month in from_wb):
            sales[article][key][month] += int(row['quantity'])
    return sales


def _next_month(month):
    return date(month.year + 1, 1, 1) if month.month == 12 else date(month.year, month.month + 1, 1)


def plan(today):
    months = full_months(today)
    stock = fbo_stock.get_data()
    rows = build(
        months,
        collect_sales(months),
        stock['items'],
        list(Exclusion.objects.values_list('text', flat=True)),
        {normalize(article) for article in GreenItem.objects.values_list('article', flat=True)},
    )
    return {
        'months': months,
        'stock_at': stock['generated_at'],
        'ozon_at': OzonMonthSales.objects.filter(month__in=months).aggregate(last=Max('synced_at'))['last'],
        'ozon_months': sorted(set(OzonMonthSales.objects.filter(month__in=months).values_list('month', flat=True))),
        'wb_months': wb_months(months),
        'rows': rows,
    }
