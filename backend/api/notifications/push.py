import json
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from pywebpush import WebPushException, webpush

from api import access

from .core import active

logger = logging.getLogger(__name__)

TTL_SEC = 6 * 60 * 60
SEND_TIMEOUT_SEC = 10
REJECTED_STATUSES = (400, 403, 404, 410)
PUSH_HOSTS = ('fcm.googleapis.com', '.push.apple.com', '.push.services.mozilla.com', '.notify.windows.com')


def _plural(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def pending(user):
    from api.models import NotificationState, PushDelivery

    items, healthy = active(user)
    seen = dict(
        NotificationState.objects.filter(user=user, seen_at__isnull=False).values_list('key', 'fingerprint')
    )
    sent = dict(PushDelivery.objects.filter(user=user).values_list('key', 'fingerprint'))
    fresh = [
        item for item in items
        if seen.get(item.key) != item.fingerprint and sent.get(item.key) != item.fingerprint
    ]
    return items, healthy, fresh


def remember(user, items):
    from api.models import PushDelivery

    for item in items:
        PushDelivery.objects.update_or_create(user=user, key=item.key, defaults={'fingerprint': item.fingerprint})


def forget_closed(user, items):
    from api.models import PushDelivery

    PushDelivery.objects.filter(user=user).exclude(key__in=[item.key for item in items]).delete()


def message(fresh):
    top = fresh[0]
    page = access.page_by_key(top.source) or {}
    if len(fresh) == 1:
        title = top.title
        body = ' '.join(part for part in (top.body, top.action) if part)
        tag = top.key
    else:
        title = f'{len(fresh)} {_plural(len(fresh), "новое дело", "новых дела", "новых дел")}'
        body = top.title
        tag = 'insights'
    return {'title': title, 'body': body, 'url': top.route or page.get('route') or '/', 'tag': tag}


def send(subscription, payload):
    try:
        webpush(
            subscription_info={
                'endpoint': subscription.endpoint,
                'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={'sub': settings.VAPID_SUBJECT},
            ttl=TTL_SEC,
            timeout=SEND_TIMEOUT_SEC,
        )
        return True
    except WebPushException as error:
        status = getattr(error.response, 'status_code', None)
        if status in REJECTED_STATUSES:
            logger.warning('Сервис пушей отверг подписку %s с кодом %s: %s', subscription.endpoint[:60], status,
                           getattr(error.response, 'text', '')[:200])
            subscription.delete()
        else:
            logger.warning('Пуш на %s не ушёл: %s', subscription.endpoint[:60], error)
        return False
    except Exception:
        logger.warning('Пуш на %s не ушёл', subscription.endpoint[:60], exc_info=True)
        return False


def is_push_endpoint(endpoint):
    url = urlparse(endpoint)
    host = url.hostname or ''
    return url.scheme == 'https' and any(host == h or (h.startswith('.') and host.endswith(h)) for h in PUSH_HOSTS)


def send_test(user):
    payload = {'title': 'Тестовое уведомление', 'body': 'Пуши на этом устройстве работают', 'url': '/', 'tag': 'test'}
    devices = list(user.push_subscriptions.all())
    return sum(send(subscription, payload) for subscription in devices), len(devices)


def subscribe(user, endpoint, p256dh, auth, user_agent=''):
    from api.models import PushSubscription

    known = PushSubscription.objects.filter(endpoint=endpoint, user=user).exists()
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={'user': user, 'p256dh': p256dh, 'auth': auth, 'user_agent': user_agent[:300]},
    )
    if not known:
        remember(user, pending(user)[2])


def unsubscribe(user, endpoint):
    from api.models import PushSubscription

    PushSubscription.objects.filter(user=user, endpoint=endpoint).delete()


def dispatch():
    stats = {'users': 0, 'pushed': 0, 'failed': 0}
    users = get_user_model().objects.filter(is_active=True, push_subscriptions__isnull=False).distinct()
    for user in users:
        stats['users'] += 1
        items, healthy, fresh = pending(user)
        if healthy:
            forget_closed(user, items)
        if not fresh:
            continue
        payload = message(fresh)
        results = [send(subscription, payload) for subscription in user.push_subscriptions.all()]
        if any(results):
            remember(user, fresh)
            stats['pushed'] += 1
        else:
            stats['failed'] += 1
    return stats
