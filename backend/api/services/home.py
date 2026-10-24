from collections import Counter
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from api import access
from api.models import UserPageEvent
from api.services.data_freshness import latest_data_update

PULSE_DAYS = 30
PULSE_PAGE = 'shipments-products'
PULSE_CACHE_PREFIX = 'home:pulse'
PULSE_CACHE_TTL = 10 * 60
VISITS_DAYS = 30
FREQUENT_LIMIT = 3


def section_visits(user, allowed):
    since = timezone.now() - timedelta(days=VISITS_DAYS)
    rows = (
        UserPageEvent.objects
        .filter(user=user, created_at__gte=since)
        .values('page_path')
        .annotate(visits=Count('id'))
    )
    visits = Counter()
    for row in rows:
        key = access.page_key_for_route(row['page_path'])
        if key in allowed:
            visits[key] += row['visits']
    return visits


def frequent_paths(visits):
    pages = (access.page_by_key(key) for key, _ in visits.most_common(FREQUENT_LIMIT))
    return [page['route'] for page in pages if page]


def _daily_shipments():
    from core.models import ShipmentItem

    today = timezone.localdate()
    start = today - timedelta(days=PULSE_DAYS - 1)
    rows = (
        ShipmentItem.objects
        .filter(shipment__date__date__gte=start, product__group='Товары', product__subgroup__isnull=False)
        .exclude(product__subgroup='')
        .annotate(day=TruncDate('shipment__date'))
        .values('day')
        .annotate(total=Sum(F('quantity') * F('price')))
    )
    totals = {row['day']: row['total'] or 0 for row in rows}
    return [
        {'date': day.isoformat(), 'value': round(float(totals.get(day, 0)))}
        for day in (start + timedelta(days=offset) for offset in range(PULSE_DAYS))
    ]


def pulse(allowed, updated_at):
    if PULSE_PAGE not in allowed:
        return None
    stamp = updated_at.isoformat() if updated_at else 'never'
    cache_key = f'{PULSE_CACHE_PREFIX}:{timezone.localdate().isoformat()}:{stamp}'
    series = cache.get(cache_key)
    if series is None:
        series = _daily_shipments()
        cache.set(cache_key, series, PULSE_CACHE_TTL)
    return {'label': 'Отгрузки за 30 дней', 'unit': '₽', 'points': series}


def home_payload(user):
    allowed = access.user_allowed_page_keys(user)
    visits = section_visits(user, allowed)
    updated_at = latest_data_update()
    return {
        'sectionVisits': dict(visits),
        'frequentPaths': frequent_paths(visits),
        'pulse': pulse(allowed, updated_at),
        'dataUpdatedAt': updated_at.isoformat() if updated_at else None,
    }
