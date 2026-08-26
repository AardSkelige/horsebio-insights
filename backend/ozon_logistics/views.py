import logging
from datetime import datetime, timezone as dt_timezone

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils.html import escape

from ozon_logistics.models import OzonOAuthToken
from ozon_logistics.services import oauth
from ozon_logistics.services.client import OzonLogisticsClient, OzonLogisticsError

logger = logging.getLogger(__name__)


def _page(title, message, *, status=200):
    """Callback открывается в браузере продавца, поэтому отвечаем страницей.

    Текст приходит из query-параметров Ozon и тела его ответа, поэтому
    экранируется: путь публичный, и подставленный скрипт выполнился бы на нашем
    домене с сессией залогиненного сотрудника.
    """
    title = escape(title)
    message = escape(message)
    html = (
        '<!doctype html><html lang="ru"><head><meta charset="utf-8">'
        f'<title>{title}</title>'
        '<style>body{font-family:system-ui,-apple-system,sans-serif;margin:0;'
        'display:flex;align-items:center;justify-content:center;min-height:100vh;'
        'background:#f6f7f9;color:#1a1a1a}main{max-width:32rem;padding:2rem;'
        'background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,.1)}'
        'h1{font-size:1.25rem;margin:0 0 .75rem}p{margin:0;line-height:1.5;color:#555}'
        '</style></head><body><main>'
        f'<h1>{title}</h1><p>{message}</p>'
        '</main></body></html>'
    )
    return HttpResponse(html, status=status)


def _superuser_only(request):
    """Токен один на всю систему: перезапустить авторизацию может только админ."""
    if not request.user.is_superuser:
        return JsonResponse({
            'status': 'error',
            'message': 'Нет доступа к этому разделу',
            'code': 'FORBIDDEN',
        }, status=403)
    return None


def oauth_start(request):
    """Отправляет продавца подтверждать доступ приложению."""
    denied = _superuser_only(request)
    if denied:
        return denied
    try:
        url, _ = oauth.build_authorize_url()
    except oauth.OzonOAuthError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)
    return HttpResponseRedirect(url)


def oauth_callback(request):
    """Принимает код авторизации от Ozon и меняет его на токен.

    Публичный путь: Ozon возвращает продавца в браузере, где сессии Инсайта
    может не быть. От подделки защищает одноразовый state.
    """
    error = request.GET.get('error')
    if error:
        description = request.GET.get('error_description', '')
        logger.warning('Ozon Доставка: отказ в авторизации: %s %s', error, description)
        return _page('Авторизация отклонена', f'{error}. {description}'.strip(), status=400)

    code = request.GET.get('code')
    state = request.GET.get('state', '')

    if not code:
        return _page('Нет кода авторизации', 'Ozon не передал параметр code.', status=400)

    if not oauth.consume_state(state):
        logger.warning('Ozon Доставка: неизвестный state в callback')
        return _page(
            'Неизвестный запрос',
            'Ссылка авторизации устарела или была открыта не с нашей стороны. '
            'Начните заново.',
            status=400,
        )

    try:
        token = oauth.exchange_code(code)
    except oauth.OzonOAuthError as exc:
        logger.error('Ozon Доставка: обмен кода не удался: %s', exc)
        return _page('Не удалось получить токен', str(exc), status=502)

    return _page(
        'Доступ выдан',
        f'Токен получен и сохранён. Действует до '
        f'{timezone.localtime(token.expires_at):%d.%m.%Y %H:%M}.',
    )


def oauth_status(request):
    """Есть ли рабочий токен — для диагностики без похода в Ozon."""
    denied = _superuser_only(request)
    if denied:
        return denied
    token = OzonOAuthToken.objects.filter(pk=OzonOAuthToken.SINGLETON_PK).first()
    if token is None:
        return JsonResponse({
            'status': 'ok',
            'authorized': False,
            'message': 'Авторизация не пройдена',
        })
    # Метки времени самого токена: по ним видно, совпадает ли наш расчёт срока
    # с тем, что считает Ozon.
    claims = oauth.token_claims(token.access_token)

    return JsonResponse({
        'status': 'ok',
        'authorized': True,
        'expires_at': token.expires_at.isoformat() if token.expires_at else None,
        'expired': token.is_expired(),
        'has_refresh_token': bool(token.refresh_token),
        'scope': token.scope,
        'token_claims': {
            'exp': claims.get('exp'),
            'exp_readable': _timestamp_to_iso(claims.get('exp')),
            'iat': claims.get('iat'),
            'iat_readable': _timestamp_to_iso(claims.get('iat')),
        },
    })


def _timestamp_to_iso(value):
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=dt_timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def diagnostics(request):
    """Живая проверка связи: реально ли открыты методы Ozon Доставки.

    Проверяем доступность доставки по номеру телефона — метод ничего не создаёт,
    но проходит весь путь: токен, Bearer, скоуп ozon-logistics.
    Вызов: /api/ozon-logistics/diag/?phone=+79161112233
    """
    denied = _superuser_only(request)
    if denied:
        return denied

    phone = request.GET.get('phone', '').strip()
    if not phone:
        return JsonResponse({
            'status': 'error',
            'message': 'Укажите номер телефона: ?phone=+79161112233',
        }, status=400)

    try:
        result = OzonLogisticsClient().delivery_check(phone)
    except (oauth.OzonOAuthError, OzonLogisticsError) as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=502)
    return JsonResponse({'status': 'ok', 'result': result})
