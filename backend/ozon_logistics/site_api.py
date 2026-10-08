"""Публичные эндпоинты для корзины horse-bio.ru.

Их дёргает JS в браузере покупателя, а не сотрудник Инсайта, поэтому:
  * сессии нет — авторизация не проверяется (путь в PUBLIC_PATHS);
  * CSRF не применим — запрос приходит с другого домена без куки;
  * зато нужен предел частоты: за каждым вызовом стоит поход в Ozon, и без
    ограничения через эти адреса можно было бы перебирать телефоны или
    исчерпать наши лимиты к API.
"""

import ipaddress
import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from ozon_logistics.models import (
    OzonAvailabilityCheck, OzonPickupPoint, OzonProduct, mask_phone,
)
from ozon_logistics.services import orders, pickup_points
from ozon_logistics.services.client import (
    OzonLogisticsClient, OzonLogisticsError, normalize_phone,
)
from ozon_logistics.services.oauth import OzonOAuthError

logger = logging.getLogger(__name__)

RATE_LIMIT_WINDOW = 60  # секунд
RATE_LIMITS = {
    # Ответ раскрывает, есть ли у номера аккаунт Ozon, — то есть сведения о
    # постороннем человеке. Лимит жёстче остальных, чтобы перебор чужих номеров
    # был бессмысленным: корзине больше десятка проверок в минуту не нужно.
    'availability': 10,
    'quote': 20,          # поход в Ozon на каждый вызов
    'points': 120,        # отдаём из своей базы, можно чаще
}
MAX_ITEMS = 100


def _client_ip(request):
    """Адрес, по которому считаем частоту запросов.

    Ни один готовый заголовок здесь не годится:

    * первый элемент X-Forwarded-For пишет сам браузер — nginx стоит
      `$proxy_add_x_forwarded_for` и **дописывает** свой адрес к присланному.
      Считать по нему значит не считать вовсе: клиент меняет заголовок на
      каждом запросе;
    * X-Real-IP и последний элемент цепочки — адрес нашего же внутреннего
      прокси. Запрос идёт `nginx фронтенда → nginx бэкенда → Django`, и
      внутренний nginx перетирает X-Real-IP своим $remote_addr. Он одинаков
      для всех покупателей, то есть весь сайт делил бы один лимит на всех.

    Поэтому идём по цепочке справа налево и берём первый публичный адрес:
    внутренние прокси сидят в приватных сетях и отсеиваются сами, а подделка
    клиента остаётся левее настоящего адреса, который дописал внешний прокси,
    и до неё очередь не доходит. Считать хопы не нужно — топология может
    поменяться, а это правило переживает и лишний прокси, и его исчезновение.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    for candidate in reversed([part.strip() for part in forwarded.split(',')]):
        try:
            address = ipaddress.ip_address(candidate)
        except ValueError:
            continue
        if address.is_global:
            return candidate
    # Ни одного публичного адреса: прокси нет вовсе или покупатель в той же
    # сети, что и мы, — тогда правду знает только сам сокет.
    return request.META.get('REMOTE_ADDR', '')


def _rate_limited(request, bucket):
    """True, если этот IP исчерпал лимит запросов в минуту."""
    limit = RATE_LIMITS[bucket]
    ip = _client_ip(request)
    key = f'ozon_site:{bucket}:{ip}'
    try:
        # Счётчик приблизительный: у файлового кеша нет атомарного инкремента
        # (cache.incr — это тот же get + set, да ещё и со сбросом срока на
        # общий TIMEOUT), поэтому параллельные запросы могут насчитать себе
        # общий первый. Для грубого предела это допустимо: он отсекает перебор,
        # а не выдаёт точную квоту.
        hits = cache.get(key, 0) + 1
        cache.set(key, hits, RATE_LIMIT_WINDOW)
    except Exception:
        # Кеш недоступен — пропускаем запрос, но не молчим об этом
        logger.warning('Ozon Доставка: кеш недоступен, предел частоты не применён')
        return False

    if hits > limit:
        # Логируем каждое превышение: по этим строкам видно перебор, если он начнётся
        logger.warning(
            'Ozon Доставка: предел частоты по %s исчерпан для %s (%s запросов)',
            bucket, ip, hits,
        )
        return True
    return False


def _foreign_origin(request):
    """Запрос из браузера с чужого домена.

    Не защита от прямых обращений (curl заголовок не шлёт), но встроить наш API
    в чужую страницу уже не выйдет. Пустой Origin пропускаем: его не будет ни у
    серверных вызовов, ни у части мобильных браузеров.
    """
    origin = request.META.get('HTTP_ORIGIN', '')
    if not origin:
        return False
    return origin not in settings.CORS_ALLOWED_ORIGINS


def _forbidden_origin(request):
    logger.warning(
        'Ozon Доставка: запрос с чужого домена %s', request.META.get('HTTP_ORIGIN', '')
    )
    return JsonResponse({'status': 'error', 'message': 'Запрос отклонён'}, status=403)


def _too_many_requests():
    return JsonResponse(
        {'status': 'error', 'message': 'Слишком много запросов, попробуйте позже'},
        status=429,
    )


def _bad_request(message):
    return JsonResponse({'status': 'error', 'message': message}, status=400)


def _upstream_error(exc):
    """Наружу не отдаём подробности ответа Ozon — они для логов."""
    logger.error('Ozon Доставка: ошибка обращения к API: %s', exc)
    return JsonResponse(
        {'status': 'error', 'message': 'Сервис доставки временно недоступен'},
        status=502,
    )


def _record_availability(request, digits, available):
    """Складывает проверку в таблицу — из неё считаем воронку корзины.

    Промах записи не должен стоить покупателю ответа: доставка ему нужнее,
    чем нам статистика. Поэтому ошибку сюда и глотаем, оставляя след в логе.
    """
    try:
        OzonAvailabilityCheck.objects.create(
            available=available,
            phone_mask=mask_phone(digits),
            ip=_client_ip(request) or None,
            referer=request.META.get('HTTP_REFERER', '')[:200],
        )
    except Exception:
        logger.exception('Ozon Доставка: проверку доступности не удалось записать')


def _payload(request):
    try:
        return json.loads(request.body or '{}')
    except ValueError:
        return None


@csrf_exempt
@require_POST
def availability(request):
    """Доступна ли покупателю доставка Ozon: {'available': bool, 'items_ok': bool}.

    Ozon отвечает по номеру телефона — по сути проверяет, может ли этот
    покупатель получить заказ в его сети. Если корзина прислала состав,
    в `items_ok` — возит ли Ozon все эти товары.
    """
    if _foreign_origin(request):
        return _forbidden_origin(request)

    if _rate_limited(request, 'availability'):
        return _too_many_requests()

    data = _payload(request)
    if data is None:
        return _bad_request('Ожидается JSON')

    phone = (data.get('phone') or '').strip()
    if not phone:
        return _bad_request('Укажите телефон')

    try:
        digits = normalize_phone(phone)
    except OzonLogisticsError as exc:
        return _bad_request(str(exc))

    try:
        result = OzonLogisticsClient().delivery_check(phone)
    except (OzonOAuthError, OzonLogisticsError) as exc:
        return _upstream_error(exc)

    available = bool(result.get('is_possible'))
    _record_availability(request, digits, available)
    response = {'status': 'ok', 'available': available}

    # Состав корзины проверяем здесь же, а не при выборе пункта: иначе покупатель
    # ищет пункт на карте и только потом узнаёт, что Ozon его заказ не повезёт
    problems = _unsellable_items(data.get('items'))
    if problems is not None:
        response['items_ok'] = not problems
        if problems:
            response['debug'] = {'code': 'items_unavailable', 'items': problems}
    return JsonResponse(response)


def _unsellable_items(raw):
    """Позиции, которые Ozon точно не повезёт, — по своей таблице, без похода в Ozon.

    None — состав не прислали или он неразборчив: тогда о товарах молчим, и
    решит расчёт при выборе пункта. Пустой список — все товары годны. Хватит ли
    остатка и возит ли Ozon в этот город, отсюда не видно: это скажет расчёт.
    """
    if not isinstance(raw, list) or not raw or len(raw) > MAX_ITEMS:
        return None
    offer_ids = [str(i.get('offer_id')).strip() for i in raw if isinstance(i, dict) and i.get('offer_id')]
    if not offer_ids:
        return None

    active = {
        p.offer_id: p
        for p in OzonProduct.objects.filter(offer_id__in=offer_ids, archived=False)
    }
    problems = []
    for offer_id in dict.fromkeys(offer_ids):
        product = active.get(offer_id)
        if product is None:
            problems.append(_unknown_product_debug(offer_id))
        elif not product.sellable_via_ozon_delivery:
            problems.append({
                'code': 'no_stocks',
                'offer_id': offer_id,
                'catalog_synced_at': product.synced_at.isoformat(),
                'hint': 'В Ozon нет остатка ни на FBS, ни на FBO — выставьте остаток и запустите синхронизацию каталога',
            })
    return problems


@require_GET
def points(request):
    """Пункты выдачи в границах карты — из нашей базы, без похода в Ozon."""
    if _foreign_origin(request):
        return _forbidden_origin(request)

    if _rate_limited(request, 'points'):
        return _too_many_requests()

    try:
        bounds = {name: float(request.GET[name]) for name in ('south', 'west', 'north', 'east')}
    except (KeyError, ValueError):
        return _bad_request('Нужны границы карты: south, west, north, east')

    if bounds['south'] > bounds['north'] or bounds['west'] > bounds['east']:
        return _bad_request('Границы карты перепутаны местами')

    found = OzonPickupPoint.in_bounds(**bounds)
    return JsonResponse({
        'status': 'ok',
        'points': [
            {'id': p.map_point_id, 'lat': p.latitude, 'lon': p.longitude, 'address': p.address}
            for p in found
        ],
    })


@require_GET
def point_details(request, map_point_id):
    """Подробности пункта: адрес, часы работы. Тянутся из Ozon однократно."""
    if _foreign_origin(request):
        return _forbidden_origin(request)

    if _rate_limited(request, 'points'):
        return _too_many_requests()

    try:
        found = pickup_points.fetch_details([map_point_id])
    except (OzonOAuthError, OzonLogisticsError) as exc:
        return _upstream_error(exc)

    if not found:
        return JsonResponse({'status': 'error', 'message': 'Пункт не найден'}, status=404)

    point = found[0]
    return JsonResponse({
        'status': 'ok',
        'point': {
            'id': point.map_point_id,
            'lat': point.latitude,
            'lon': point.longitude,
            'name': point.name,
            'address': point.address,
            'details': point.details,
        },
    })


def _parse_destination(data):
    """Куда везём: пункт выдачи или координаты курьера. Ровно одно из двух.

    Разбираем здесь, а не в клиенте: там любая нечисловая строка обрывается
    ValueError и покупатель получает 500 вместо внятного отказа.
    """
    map_point_id = data.get('map_point_id')
    coordinates = data.get('coordinates')

    if map_point_id in (None, '') and not coordinates:
        raise ValueError('Выберите пункт выдачи или укажите адрес')
    if map_point_id not in (None, '') and coordinates:
        raise ValueError('Укажите либо пункт выдачи, либо координаты — не оба сразу')

    if map_point_id not in (None, ''):
        try:
            return int(map_point_id), None
        except (TypeError, ValueError):
            raise ValueError('Пункт выдачи задаётся числовым идентификатором')

    if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
        raise ValueError('Координаты задаются парой: широта и долгота')
    try:
        latitude, longitude = (float(value) for value in coordinates)
    except (TypeError, ValueError):
        raise ValueError('Координаты должны быть числами')
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Координаты вне допустимых пределов')
    return None, (latitude, longitude)


class UnknownProduct(ValueError):
    """Артикула корзины нет в таблице товаров Ozon — sku взять неоткуда."""

    def __init__(self, offer_id):
        self.offer_id = offer_id
        super().__init__(f'Товар {offer_id or "?"} недоступен для доставки Ozon')


def _unknown_product_debug(offer_id):
    """Почему артикул не нашёлся — для консоли браузера, покупатель её не видит.

    Отличаем случаи, ведущие в разные места: каталог не синхронизирован вовсе,
    карточка в архиве, артикул в Ozon записан иначе, чем на сайте, или карточки
    в Ozon нет.
    """
    total = OzonProduct.objects.count()
    last_sync = OzonProduct.objects.aggregate(last=Max('synced_at'))['last']
    debug = {
        'code': 'unknown_offer_id',
        'offer_id': offer_id,
        'catalog_size': total,
        'catalog_synced_at': last_sync.isoformat() if last_sync else None,
    }
    if not total:
        debug['hint'] = 'Таблица товаров Ozon пуста: синхронизация каталога (sync_ozon_products) не запускалась или падает'
        return debug

    similar = OzonProduct.objects.filter(offer_id__iexact=(offer_id or '').strip()).first()
    if similar and similar.archived:
        debug['hint'] = (
            f'Карточка «{similar.offer_id}» в архиве Ozon. Если её достали из архива — '
            'запустите синхронизацию каталога'
        )
    elif similar:
        debug['hint'] = f'В Ozon артикул записан как «{similar.offer_id}» — расходится с сайтом регистром или пробелами'
    else:
        debug['hint'] = (
            'Артикула нет в каталоге Ozon по последней синхронизации: карточки на Ozon нет, '
            'артикул на сайте и в Ozon разный, или каталог давно не обновлялся'
        )
    return debug


def _unavailable_debug(saved):
    """Что ответил Ozon по каждой посылке, если доставить нельзя."""
    return {
        'code': 'ozon_unavailable',
        'splits': [
            {
                'items': [
                    {'offer_id': i.get('offer_id'), 'sku': i.get('sku'), 'quantity': i.get('quantity')}
                    for i in split.get('items') or []
                ],
                'warehouse_id': split.get('warehouse_id'),
                'delivery_schema': split.get('delivery_schema'),
                'available': bool(split.get('commissions')),
                'unavailable_reason': split.get('unavailable_reason'),
                'method_unavailable_reason': (split.get('delivery_method') or {}).get('unavailable_reason'),
            }
            for split in saved.splits
        ],
    }


def _parse_items(raw):
    """Позиции корзины → список для Ozon. Артикулы переводим в sku по своей таблице."""
    if not isinstance(raw, list) or not raw:
        raise ValueError('Список товаров пуст')
    if len(raw) > MAX_ITEMS:
        raise ValueError('Слишком много позиций в заказе')

    offer_ids = [str(i.get('offer_id')) for i in raw if i.get('offer_id') and not i.get('sku')]
    by_offer_id = {
        p.offer_id: p.sku
        for p in OzonProduct.objects.filter(offer_id__in=offer_ids, archived=False)
    } if offer_ids else {}

    items = []
    for entry in raw:
        try:
            quantity = int(entry.get('quantity', 1))
        except (TypeError, ValueError):
            raise ValueError('Количество должно быть числом')
        if quantity < 1:
            raise ValueError('Количество должно быть больше нуля')

        sku = entry.get('sku') or by_offer_id.get(str(entry.get('offer_id')))
        if not sku:
            raise UnknownProduct(entry.get('offer_id'))
        items.append({'sku': int(sku), 'quantity': quantity})
    return items


@csrf_exempt
@require_POST
def quote(request):
    """Расчёт доставки. Возвращает идентификатор, срок и стоимость.

    Идентификатор кладётся в скрытое поле формы заказа: по нему после оплаты
    мы найдём этот расчёт и создадим заказ в Ozon.
    """
    if _foreign_origin(request):
        return _forbidden_origin(request)

    if _rate_limited(request, 'quote'):
        return _too_many_requests()

    data = _payload(request)
    if data is None:
        return _bad_request('Ожидается JSON')

    phone = (data.get('phone') or '').strip()
    if not phone:
        return _bad_request('Укажите телефон')

    try:
        items = _parse_items(data.get('items'))
    except UnknownProduct as exc:
        return JsonResponse(
            {'status': 'error', 'message': str(exc), 'debug': _unknown_product_debug(exc.offer_id)},
            status=400,
        )
    except ValueError as exc:
        return _bad_request(str(exc))

    try:
        map_point_id, coordinates = _parse_destination(data)
    except ValueError as exc:
        return _bad_request(str(exc))

    try:
        saved = orders.create_quote(
            phone=phone,
            items=items,
            map_point_id=map_point_id,
            coordinates=coordinates,
            courier_address=data.get('address'),
        )
    except (OzonOAuthError, OzonLogisticsError) as exc:
        return _upstream_error(exc)

    if not saved.is_deliverable:
        return JsonResponse({
            'status': 'ok',
            'available': False,
            'reasons': saved.unavailable_reasons(),
            'debug': _unavailable_debug(saved),
        })

    return JsonResponse({
        'status': 'ok',
        'available': True,
        'quote_id': str(saved.id),
        'delivery_cost': float(saved.delivery_cost or 0),
        'dates': _delivery_dates(saved),
    })


def _delivery_dates(saved):
    """Ближайший срок доставки по каждому отправлению — для показа в корзине."""
    dates = []
    for split in saved.splits:
        if not split.get('commissions'):
            continue
        timeslots = (split.get('delivery_method') or {}).get('timeslots') or []
        if timeslots:
            dates.append(timeslots[0].get('logistic_date_range'))
    return dates
