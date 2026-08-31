"""OAuth 2.0 для частного приложения Ozon Доставки.

Флоу — authorization_code с однократным подтверждением продавца
(client_credentials для Seller API не работает, проверено: отдаёт 400).
Подробности и добытые эмпирически факты — в docs/ozon-logistics.md
(каталог docs/ ведётся локально и в репозиторий не коммитится).
"""

import base64
import binascii
import json
import logging
import os
import secrets
from datetime import datetime, timezone as dt_timezone
from urllib.parse import urlencode

import requests
from django.db import transaction
from django.utils import timezone

from ozon_logistics.models import OzonOAuthToken, OzonAuthState

logger = logging.getLogger(__name__)

AUTHORIZE_URL = 'https://seller.ozon.ru/app/appstore/oauth/authorize'
TOKEN_URL = 'https://xapi.ozon.ru/oauth/token'
DEFAULT_TIMEOUT = 30

# Скоупы приложения «OZON Доставка Horse-Bio». Держать синхронно с ЛК: менять
# их там — значит отправить приложение на повторную модерацию.
SCOPES = [
    'seller-api.ozon-logistics',
    'seller-api.posting-fbs',
    'seller-api.posting-fbo',
    'seller-api.warehouse',
    'seller-api.notification',
    'seller-api.product',
    'seller-api.returns',
    'seller-api.report',
]

# Если Ozon не сообщил срок жизни токена и его не удалось прочитать из JWT.
FALLBACK_LIFETIME = timezone.timedelta(hours=1)

# Верхняя граница правдоподобной длительности жизни токена: всё, что больше,
# считаем не длительностью, а чем-то другим, и не используем.
MAX_PLAUSIBLE_LIFETIME = timezone.timedelta(days=90)


class OzonOAuthError(RuntimeError):
    """Ошибка авторизации: нет кредов, отказ Ozon, отсутствует токен."""


def _credentials():
    client_id = os.getenv('OZON_LOGISTICS_CLIENT_ID')
    client_secret = os.getenv('OZON_LOGISTICS_CLIENT_SECRET')
    if not client_id or not client_secret:
        raise OzonOAuthError(
            'Не заданы OZON_LOGISTICS_CLIENT_ID / OZON_LOGISTICS_CLIENT_SECRET'
        )
    return client_id, client_secret


def redirect_uri():
    uri = os.getenv('OZON_LOGISTICS_REDIRECT_URI')
    if not uri:
        raise OzonOAuthError('Не задан OZON_LOGISTICS_REDIRECT_URI')
    return uri


def build_authorize_url():
    """Ссылка, по которой продавец подтверждает доступ. Возвращает (url, state).

    access_type=offline обязателен — иначе Ozon не выдаст refresh_token и
    переавторизовываться придётся руками после каждого истечения.
    """
    client_id, _ = _credentials()
    state = secrets.token_urlsafe(32)[:64]

    OzonAuthState.purge_expired()
    OzonAuthState.objects.create(state=state)

    params = {
        'response_type': 'code',
        'access_type': 'offline',
        'client_id': client_id,
        'redirect_uri': redirect_uri(),
        'scope': ' '.join(SCOPES),
        'state': state,
        'prompt': 'select_company',
    }
    return f'{AUTHORIZE_URL}?{urlencode(params)}', state


def consume_state(state):
    """Гасит одноразовый state. False — если он неизвестен или просрочен."""
    OzonAuthState.purge_expired()
    deleted, _ = OzonAuthState.objects.filter(state=state).delete()
    return deleted > 0


def token_claims(token):
    """Payload JWT без проверки подписи, {} — если разобрать не удалось.

    Подпись не проверяем сознательно: токен пришёл от Ozon по TLS, а нам нужны
    только его собственные метки времени.
    """
    try:
        payload_b64 = token.split('.')[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _expiry_from_jwt(token):
    """Срок из самого токена — авторитетный источник: по нему Ozon его и проверяет."""
    exp = token_claims(token).get('exp')
    if not exp:
        return None
    try:
        return datetime.fromtimestamp(int(exp), tz=dt_timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _expiry_from_expires_in(value):
    """Срок из поля expires_in — только если оно правдоподобно как длительность.

    Ozon прислал здесь около 1.79e9 — это 57 лет, столько access-токены не живут.
    Что означает такое значение, документация не объясняет, поэтому вместо догадок
    отбрасываем его и полагаемся на exp в JWT.
    """
    if value in (None, ''):
        return None
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        logger.warning('Ozon Доставка: нечисловой expires_in: %r', value)
        return None
    if not 0 < seconds <= MAX_PLAUSIBLE_LIFETIME.total_seconds():
        logger.warning(
            'Ozon Доставка: expires_in=%s вне разумных пределов, игнорирую', seconds
        )
        return None
    return timezone.now() + timezone.timedelta(seconds=seconds)


def _post_token(payload):
    try:
        response = requests.post(
            TOKEN_URL,
            json=payload,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise OzonOAuthError(f'Ozon недоступен: {exc}') from exc

    if response.status_code != 200:
        # В теле бывает осмысленное объяснение отказа — оно важнее кода.
        raise OzonOAuthError(
            f'Ozon отклонил запрос токена (HTTP {response.status_code}): {response.text[:500]}'
        )

    try:
        return response.json()
    except ValueError as exc:
        raise OzonOAuthError(f'Ozon вернул не JSON: {response.text[:500]}') from exc


def _store(data, *, previous_refresh=''):
    """Сохраняет ответ Ozon в единственную запись токена."""
    access_token = data.get('access_token')
    if not access_token:
        raise OzonOAuthError(f'В ответе Ozon нет access_token: {list(data)}')

    expires_at = (
        _expiry_from_jwt(access_token)
        or _expiry_from_expires_in(data.get('expires_in'))
        or timezone.now() + FALLBACK_LIFETIME
    )

    scope = data.get('scope') or ''
    if isinstance(scope, (list, tuple)):
        scope = ' '.join(scope)

    token, _ = OzonOAuthToken.objects.update_or_create(
        pk=OzonOAuthToken.SINGLETON_PK,
        defaults={
            'access_token': access_token,
            # Ozon не всегда присылает refresh при обновлении — старый остаётся рабочим.
            'refresh_token': data.get('refresh_token') or previous_refresh,
            'expires_at': expires_at,
            'scope': scope,
        },
    )
    return token


def exchange_code(code):
    """Меняет код авторизации на токен. Код живёт 5 минут."""
    client_id, client_secret = _credentials()
    data = _post_token({
        'grant_type': 'authorization_code',
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri(),
        'code': code,
    })
    # Ozon может не вернуть refresh_token в ответе на повторную авторизацию —
    # затирать рабочий пустой строкой нельзя, иначе обновлять будет нечем.
    previous = OzonOAuthToken.objects.filter(pk=OzonOAuthToken.SINGLETON_PK).first()
    token = _store(data, previous_refresh=previous.refresh_token if previous else '')
    logger.info('Ozon Доставка: получен токен, истекает %s', token.expires_at)
    return token


def _refresh(token):
    if not token.refresh_token:
        raise OzonOAuthError(
            'Токен истёк, а refresh_token отсутствует — нужна повторная авторизация продавца'
        )
    client_id, client_secret = _credentials()
    data = _post_token({
        'grant_type': 'refresh_token',
        'client_id': client_id,
        'client_secret': client_secret,
        'refresh_token': token.refresh_token,
    })
    refreshed = _store(data, previous_refresh=token.refresh_token)
    logger.info('Ozon Доставка: токен обновлён, истекает %s', refreshed.expires_at)
    return refreshed


def get_valid_token(*, force_refresh=False):
    """Единственная точка получения токена: обновит, если пора, и вернёт строку.

    Обновление идёт под блокировкой строки: периодические задачи ходят из cron
    параллельно с веб-запросами, и два одновременных refresh отдали бы второму
    процессу уже отозванный токен.
    """
    with transaction.atomic():
        token = (
            OzonOAuthToken.objects
            .select_for_update()
            .filter(pk=OzonOAuthToken.SINGLETON_PK)
            .first()
        )
        if token is None:
            raise OzonOAuthError(
                'Нет сохранённого токена — пройдите авторизацию '
                '(GET /api/ozon-logistics/oauth/start/)'
            )
        if force_refresh or token.is_expired():
            token = _refresh(token)
        return token.access_token
