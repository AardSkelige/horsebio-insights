from datetime import timedelta

from django.utils import timezone

from production_plan.services import wb_sales

from .core import CRITICAL, WARNING, Notification, provider

STALE_DAYS = 2
KEY_WARN_DAYS = 30
RENEW = 'Серёже: перевыпустить персональный токен «Статистика» в ЛК WB и обновить WB_STATS_TOKEN в .env.prod и секрете BACKEND_ENV_PROD'


def stale_wb_sales(today):
    loaded = wb_sales.state()
    last = timezone.localtime(loaded.synced_at).date() if loaded else None
    if last and (today - last).days <= STALE_DAYS:
        return
    yield Notification(
        key='production-plan:wb-stale',
        level=WARNING,
        title='Продажи WB не обновляются',
        body=f'Последняя загрузка {last:%d.%m.%Y}' if last else 'Заказы WB ещё ни разу не загружались',
        action='Пока продажи не загрузятся, новые месяцы WB считаются по нашим отгрузкам. Проверьте ключ WB и ночную задачу',
        fingerprint=str(last),
    )


def expiring_wb_key(today):
    until = wb_sales.expires()
    if until is None or until - today > timedelta(days=KEY_WARN_DAYS):
        return
    expired = until <= today
    yield Notification(
        key='production-plan:wb-key',
        level=CRITICAL if expired else WARNING,
        title='Ключ WB истёк' if expired else 'Ключ WB скоро истечёт',
        body=f'Действует до {until:%d.%m.%Y}',
        action=RENEW,
        fingerprint=f'{until}:{expired}',
    )


@provider('production-plan')
def production_plan_notifications():
    if not wb_sales.configured():
        return
    today = timezone.localdate()
    yield from stale_wb_sales(today)
    yield from expiring_wb_key(today)
