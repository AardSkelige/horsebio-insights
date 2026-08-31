"""Ядро уведомлений Insights.

Уведомление здесь — не событие, а **условие**: правило, которое считается заново
по живым данным при каждом запросе. Ничего не копится в базе, и поэтому ничего
не протухает: как только условие перестало выполняться, уведомление исчезает
само. Это модель из систем мониторинга (Prometheus Alertmanager), и она подходит
нам ровно потому, что все наши поводы — состояния, а не факты: «остаток на сайте
разошёлся» верно ровно до тех пор, пока остатки не сойдутся.

Отсюда же — **отпечаток** (`fingerprint`): строка из значений, которые составляют
суть уведомления. Пока он не меняется, уведомление то же самое и остаётся
прочитанным; как только меняется — отметка слетает, и человек видит уведомление
снова. Поэтому в отпечаток не кладут то, что меняется само по себе (например,
«осталось дней»), иначе уведомление становилось бы непрочитанным каждую ночь.

Больше состояний у уведомления нет: оно либо прочитано, либо нет, и отметку
человек ставит и снимает сам. Удалить уведомление нельзя — проблема от этого
не исчезнет, а исчезает оно само, когда условие перестало выполняться.

Разделы подключаются провайдерами:

    @provider('discounted')
    def discounted_notifications():
        yield Notification(key=..., level=WARNING, title=..., ...)

`source` провайдера — ключ страницы из `api.access.PAGES`. Он же решает, кому
уведомление видно: раздел, к которому у человека нет доступа, до него не дойдёт.
Отсюда же берутся название раздела и маршрут — дублировать их в провайдере
не нужно.
"""

import hashlib
import logging
from dataclasses import dataclass, field

from django.core.cache import cache
from django.utils import timezone

from api import access

logger = logging.getLogger(__name__)

# Уровни — по тому, что случится, если не отреагировать.
CRITICAL = 'critical'   # так делать нельзя: нарушается регламент или закон
WARNING = 'warning'     # можно потерять деньги или подвести покупателя
INFO = 'info'           # просто стоит знать

LEVELS = (CRITICAL, WARNING, INFO)
_LEVEL_ORDER = {level: index for index, level in enumerate(LEVELS)}


def _rank(level):
    """Порядок уровня. Неизвестный уровень — в конец, а не исключение.

    Опечатка в провайдере не должна ронять весь колокольчик: ради этого
    в `_collect_source` и стоит перехват, и здесь его нельзя обойти.
    """
    return _LEVEL_ORDER.get(level, len(LEVELS))

# Провайдер отвечает на запрос из интерфейса, поэтому его результат кешируется:
# внутри он обычно ходит во внешние системы. Кеш общий для всех пользователей —
# уведомления считаются по данным компании, персонально только отметки.
CACHE_TTL = 5 * 60
CACHE_PREFIX = 'notifications'

_PROVIDERS = {}


@dataclass
class Notification:
    """Одно уведомление.

    key         — устойчивый идентификатор вида `<раздел>:<правило>:<объект>`.
                  По нему хранятся персональные отметки, поэтому он не должен
                  меняться от пересчёта к пересчёту.
    level       — CRITICAL / WARNING / INFO.
    title       — что произошло; читается за секунду, с именем объекта.
    body        — подробности: цифры, из которых сделан вывод.
    action      — что человеку сделать. Одна конкретная инструкция, а не совет.
    fingerprint — суть уведомления; меняется — отметки сбрасываются.
    links       — внешние ссылки [(подпись, адрес)]: МойСклад, страница на сайте.
    """

    key: str
    level: str
    title: str
    body: str = ''
    action: str = ''
    fingerprint: str = ''
    links: list = field(default_factory=list)
    # Проставляется реестром из ключа провайдера — руками задавать не нужно
    source: str = ''


def provider(source):
    """Зарегистрировать провайдера уведомлений раздела.

    `source` — ключ страницы из `api.access.PAGES`: он определяет и видимость
    по правам, и подпись раздела в интерфейсе.
    """
    def decorator(func):
        _PROVIDERS[source] = func
        return func
    return decorator


def _fingerprint(notification):
    """Отпечаток по умолчанию — сам текст уведомления.

    Провайдер может задать его явно и обычно так и делает: текст меняется от
    правки формулировки, а отпечаток должен меняться только от сути.
    """
    if notification.fingerprint:
        return notification.fingerprint
    raw = f'{notification.level}|{notification.title}|{notification.body}'
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def _collect_source(source, func, refresh=False):
    """Уведомления одного раздела, с кешем и изоляцией ошибок.

    Раздел, который не смог посчитаться (МойСклад не ответил, сайт лежит),
    не должен ронять весь колокольчик — остальные разделы важнее.
    """
    cache_key = f'{CACHE_PREFIX}:{source}'
    if refresh:
        cache.delete(cache_key)
    else:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    try:
        items = list(func() or [])
    except Exception:
        # None, а не пустой список: «раздел не смог посчитаться» и «в разделе
        # ничего нет» — разные вещи, и вторая разрешает чистить отметки
        logger.warning('Провайдер уведомлений «%s» упал', source, exc_info=True)
        return None

    for item in items:
        item.source = source
        item.fingerprint = _fingerprint(item)
    cache.set(cache_key, items, CACHE_TTL)
    return items


def invalidate(source):
    """Сбросить кеш уведомлений раздела.

    Зовётся из самого раздела после действия, которое меняет положение дел:
    иначе колокольчик до пяти минут показывает то, что человек уже исправил.
    """
    cache.delete(f'{CACHE_PREFIX}:{source}')


def _states_for(user, active_keys, prune=True):
    """Отметки пользователя, попутно вычищая те, чей повод уже закрыт.

    Это не уборка мусора, а часть смысла: уведомление живёт, пока выполняется
    условие, и вместе с условием должна уходить отметка. Иначе раскупленный
    товар, который прочитали, довезли и раскупили снова, останется прочитанным
    навсегда — отпечаток у повода один и тот же, и колокольчик промолчит.

    prune=False — когда какой-то раздел не посчитался: его уведомлений в списке
    нет, но поводы там могли и остаться, а стереть отметку значит показать
    человеку как новое то, что он уже читал.
    """
    from api.models import NotificationState

    rows = list(NotificationState.objects.filter(user=user))
    if prune:
        stale = [row.pk for row in rows if row.key not in active_keys]
        if stale:
            NotificationState.objects.filter(pk__in=stale).delete()
    return {row.key: row for row in rows if row.key in active_keys}


def _serialize(notification, state):
    """Уведомление плюс отметка о прочтении этого пользователя.

    Отметка действует, только пока отпечаток тот же: изменилась суть — человек
    видит уведомление как новое, даже если читал предыдущую его версию.
    """
    same = state is not None and state.fingerprint == notification.fingerprint
    page = access.page_by_key(notification.source) or {}
    return {
        'key': notification.key,
        'source': notification.source,
        'source_label': page.get('label', notification.source),
        'route': page.get('route', ''),
        'level': notification.level,
        'title': notification.title,
        'body': notification.body,
        'action': notification.action,
        'links': [{'label': label, 'url': url} for label, url in notification.links],
        'seen': bool(same and state.seen_at),
    }


def active(user, refresh=False):
    """Уведомления, актуальные для этого пользователя, без персональных отметок.

    Возвращает `(уведомления, всё_посчиталось)`. Второе нужно уборке отметок:
    если раздел не ответил, его уведомлений в списке нет — но это не значит,
    что поводы закрыты.
    """
    allowed = access.user_allowed_page_keys(user)
    items = []
    healthy = True
    for source, func in _PROVIDERS.items():
        if source not in allowed:
            continue
        collected = _collect_source(source, func, refresh=refresh)
        if collected is None:
            healthy = False
            continue
        items.extend(collected)
    items.sort(key=lambda n: (_rank(n.level), n.source, n.key))
    return items, healthy


def collect(user, refresh=False):
    """Полный ответ для интерфейса: список, счётчики и разбивка по разделам.

    Счётчик непрочитанных считается по разделам тоже: по нему в меню загорается
    точка, и человек видит, где именно появилось дело.
    """
    items, healthy = active(user, refresh=refresh)
    states = _states_for(user, {item.key for item in items}, prune=healthy)
    payload = [_serialize(item, states.get(item.key)) for item in items]

    by_source = {}
    for item in payload:
        stats = by_source.setdefault(item['source'], {
            'label': item['source_label'],
            'route': item['route'],
            'total': 0,
            'unseen': 0,
            'level': None,
        })
        stats['total'] += 1
        if not item['seen']:
            stats['unseen'] += 1
            # Цвет точки в меню — по самому серьёзному непрочитанному: точка и
            # горит только пока непрочитанные есть, и прочитанное не должно
            # оставлять её красной
            if stats['level'] is None or _rank(item['level']) < _rank(stats['level']):
                stats['level'] = item['level']

    unread = [item for item in payload if not item['seen']]
    return {
        'items': payload,
        'counts': {
            'total': len(payload),
            'unseen': len(unread),
            # Уровень значка считается по непрочитанным, а не по всему списку:
            # иначе одно прочитанное критическое красило бы точку в красный,
            # когда нового осталось только информационное
            'level': min((item['level'] for item in unread), key=_rank, default=None),
            **{level: sum(1 for item in payload if item['level'] == level) for level in LEVELS},
        },
        'by_source': by_source,
        'generated_at': timezone.now().isoformat(timespec='seconds'),
    }


def mark_read(user, keys, read=True):
    """Отметить уведомления прочитанными или вернуть в непрочитанные.

    Пустой список ключей означает «все» — так работает «Прочитать всё».

    Отпечаток берём из живого пересчёта, а не из запроса: интерфейс мог
    открыться час назад, и пометить надо ровно то, что человек видел, — если
    за это время суть изменилась, отметка не приклеится.
    """
    from api.models import NotificationState

    # Строку принимаем как один ключ: иначе `set('a:b')` рассыпался бы на буквы,
    # ни один ключ не совпал бы, и отметка молча не поставилась
    if isinstance(keys, str):
        keys = [keys]
    wanted = set(keys or [])
    now = timezone.now()
    touched = []
    items, _ = active(user)
    for item in items:
        if wanted and item.key not in wanted:
            continue
        NotificationState.objects.update_or_create(
            user=user, key=item.key,
            defaults={'fingerprint': item.fingerprint, 'seen_at': now if read else None},
        )
        touched.append(item.key)
    return touched
