"""Сведения о доставке Ozon в заказе МойСклада.

Заказ сайта и заказ Ozon живут порознь: первый заводит демон 06 по письму об
оплате, второй создаёт наш робот, и связывает их только номер заказа сайта
(`externalCode` в МойСкладе, `site_order_id` в расчёте). Из-за этого сотрудник,
открыв заказ в МойСкладе, не видел ни номера заказа Ozon, ни отправлений — и
найти посылку в личном кабинете Ozon было не по чему.

Пишем в комментарий заказа своим блоком строк, приёмом робота накладных СДЭК:
читаем свежий комментарий, снимаем прежние свои строки, ставим новые. Так
правка сотрудника переживает прогон, а блок не размножается.

Здесь же — статус «Отгружен». Его ставит не сотрудник: как только Ozon сообщает,
что посылка поехала, статус меняем мы, а отгрузку по нему создаёт сценарий
МойСклада. Ровно так же работает чужая синхронизация с маркетплейсом: `delivering`
у Ozon → «Отгружен» в МойСкладе → сценарий.

При схеме MIX посылка может уехать и со склада Ozon. Тот товар в МойСкладе
списан ещё при поставке на FBO, поэтому перед статусом создаём возврат от Озона
(см. ms_returns) — иначе отгрузка списала бы ту же единицу второй раз. Возврат
проводится первым: сценарий создаёт отгрузку через считаные секунды после
статуса, и опоздавший возврат уже ничего не спасёт.

Не собрали возврат — статус не ставим вовсе: заказ уходит в уведомления
раздела «Заказы сайта», разбирается человек.
"""

import logging

from django.db.models import Q
from django.utils import timezone

from ozon_logistics.models import OzonDeliveryQuote, OzonPosting
from ozon_logistics.services import ms_client, ms_returns
from ozon_logistics.services.ms_client import MoyskladError  # noqa: F401  (зовут снаружи)

logger = logging.getLogger(__name__)

# Статус «Отгружен» в заказе покупателя: по его появлению сценарий МойСклада
# создаёт отгрузку. Id взят из метаданных живого аккаунта.
SHIPPED_STATE_ID = '41e679a5-266b-11eb-0a80-090200155c9e'

# Статусы заказа, при которых отгрузка либо уже случилась, либо не случится
# никогда. В них не вмешиваемся: там или сценарий уже отработал, или человек
# решил иначе. Id — из метаданных заказа покупателя.
HANDS_OFF_STATE_IDS = {
    SHIPPED_STATE_ID,                          # Отгружен
    '054151a0-0ba2-11ef-0a80-113c003f68c8',    # В доставке
    'f9c2c244-e445-11ee-0a80-168700247bfe',    # Доставлен
    '41e67a4d-266b-11eb-0a80-090200155ca0',    # Возврат
    '41e67be8-266b-11eb-0a80-090200155ca1',    # Отменен
    'a39c3342-e445-11ee-0a80-1687002476d1',    # Не принят на СЦ
    'b040db3b-e445-11ee-0a80-062400246d65',    # Спор
    '5f4d29cc-72c2-11f0-0a80-1bbb00c0822d',    # Отказ
}

# Статусы отправления, после которых товар от нас уже уехал. Порог тот же, что
# у чужой синхронизации: она ставит «Отгружен» на delivering (сверено на пяти
# заказах маркетплейса, отставание 2-5 минут).
SHIPPED_STATUSES = {'delivering', 'delivered'}

# Заказ, ждущий решения человека, перечитываем не чаще этого: он может провисеть
# неделями, а лимит запросов в МойСкладе общий на весь аккаунт.
RECHECK_AFTER = timezone.timedelta(hours=1)

# Что делать с отгрузкой, когда посылка уехала
SHIP_OURSELVES = 'ourselves'   # всё со своего склада — статус можно ставить сразу
SHIP_WITH_RETURN = 'with_return'  # часть уехала с FBO — сперва возврат от Озона

ORDER_LINE_PREFIX = 'Заказ Ozon Доставки:'
POSTING_LINE_PREFIX = 'Отправление '
RETURN_LINE_PREFIX = 'Возврат от Озона:'
CABINET_PREFIX = 'https://seller.ozon.ru/app/postings/'

# Статусы отправления по-русски: в комментарий заказа смотрит человек, а не робот.
STATUS_NAMES = {
    'acceptance_in_progress': 'идёт приёмка',
    'arbitration': 'арбитраж',
    'awaiting_approve': 'ожидает подтверждения',
    'awaiting_deliver': 'ожидает отгрузки',
    'awaiting_packaging': 'ожидает упаковки',
    'awaiting_registration': 'ожидает регистрации',
    'awaiting_verification': 'создано',
    'cancelled': 'отменено',
    'cancelled_from_split_pending': 'отменено из-за разделения',
    'client_arbitration': 'клиентский арбитраж доставки',
    'delivered': 'доставлено',
    'delivering': 'доставляется',
    'driver_pickup': 'у водителя',
    'not_accepted': 'не принято на сортировочном центре',
}


def cabinet_url(posting_number, schema):
    """Ссылка на отправление в кабинете продавца.

    Адреса у схем разные — так они устроены в самом кабинете:
    FBO открывается путём, FBS — параметром.
    """
    if schema == OzonPosting.SCHEMA_FBO:
        return f'{CABINET_PREFIX}fbo/{posting_number}'
    return f'{CABINET_PREFIX}fbs?postingDetails={posting_number}'


def is_managed_line(line):
    """Строка комментария, которую пишет этот робот."""
    text = line.strip()
    return (text.startswith(ORDER_LINE_PREFIX)
            or text.startswith(POSTING_LINE_PREFIX)
            or text.startswith(RETURN_LINE_PREFIX)
            or text.startswith(CABINET_PREFIX))


def build_block(quote, postings):
    """Строки для комментария заказа: номер заказа Ozon и его отправления.

    Отправления появляются не сразу — сначала в заказе будет одна строка с
    номером, остальные допишутся, когда их увидит робот статусов.
    """
    if not quote.order_number:
        return []

    lines = [f'{ORDER_LINE_PREFIX} {quote.order_number}']
    for posting in postings:
        status = STATUS_NAMES.get(posting.status, posting.status or 'статус неизвестен')
        # Схему пишем коротко (FBS/FBO), а не расшифровкой из модели: в строке
        # уже есть тире, и второе превращает её в кашу.
        lines.append(
            f'{POSTING_LINE_PREFIX}{posting.posting_number} — '
            f'{posting.schema.upper()}, {status}'
        )
        lines.append(cabinet_url(posting.posting_number, posting.schema))
    if quote.ms_return:
        lines.append(
            f'{RETURN_LINE_PREFIX} {quote.ms_return} — товар уехал со склада FBO, '
            'забрали его у Озона, чтобы не списать дважды'
        )
    return lines


def merge_description(description, block):
    """Свой блок внизу комментария, чужой текст — нетронутым сверху."""
    kept = [line for line in (description or '').split('\n') if not is_managed_line(line)]
    base = '\n'.join(kept).rstrip()
    return '\n'.join(([base] if base else []) + block).strip()


def _quotes_to_sync():
    """Заказы Ozon, у которых есть куда писать: создан заказ и известен заказ сайта."""
    return (
        OzonDeliveryQuote.objects
        .filter(status=OzonDeliveryQuote.STATUS_ORDERED)
        .exclude(order_number='')
        .exclude(site_order_id='')
        .prefetch_related('postings_tracked')
        .order_by('created_at')
    )


def shipping_decision(postings):
    """Уехал ли заказ от нас и можем ли мы закрыть его отгрузкой сами.

    None — ещё едет или ещё не собран; трогать нечего.
    """
    alive = [p for p in postings if p.status not in OzonPosting.ALARMING_STATUSES]
    if not alive:
        # Всё отменено — это не отгрузка, а повод вернуть деньги; им занимаются
        # уведомления раздела «Заказы сайта».
        return None
    if not all(p.status in SHIPPED_STATUSES for p in alive):
        return None
    if any(p.schema == OzonPosting.SCHEMA_FBO for p in alive):
        return SHIP_WITH_RETURN
    return SHIP_OURSELVES


def awaiting_manual_shipment():
    """Заказы с FBO, которые робот закрыть не смог: ждут человека.

    Считается по своей базе, без похода в МойСклад: это же условие показывают
    уведомления, а они пересчитываются на каждый запрос страницы.

    Условие — не «уехало с FBO», а «робот уже пробовал и не смог»: между
    появлением статуса `delivering` и ближайшим прогоном проходит до пяти
    минут, и звать человека в это окно незачем. Отметку о походе в МойСклад
    робот ставит сам, так что непустой `ms_checked_at` и означает «пробовал».
    """
    quotes = _quotes_to_sync().filter(
        ms_shipped_at__isnull=True, ms_return='', ms_checked_at__isnull=False,
    )
    for quote in quotes:
        postings = sorted(quote.postings_tracked.all(), key=lambda p: p.posting_number)
        if shipping_decision(postings) == SHIP_WITH_RETURN:
            # Отменённое отправление никуда не уехало и в возврат не входит —
            # человеку показываем только то, что реально требует документа.
            yield quote, [p for p in postings
                          if p.status not in OzonPosting.ALARMING_STATUSES]


def _state_id(order):
    href = ((order.get('state') or {}).get('meta') or {}).get('href', '')
    return href.rsplit('/', 1)[-1]


def _rechecked_recently(quote):
    return (quote.ms_checked_at is not None
            and quote.ms_checked_at >= timezone.now() - RECHECK_AFTER)


def _needs_moysklad(quote, *, note_changed, decision):
    """Идти ли в МойСклад за этим заказом на этом прогоне."""
    if note_changed:
        # Ни разу ничего не записали, хотя ходили: скорее всего заказа сайта в
        # МойСкладе ещё нет. Такой расчёт может висеть неделями — не дёргаем
        # МойСклад каждые пять минут, ждём следующей проверки.
        if not quote.ms_note and _rechecked_recently(quote):
            return False
        return True
    if quote.ms_shipped_at or decision is None:
        return False
    if decision == SHIP_OURSELVES:
        return True
    if quote.ms_return:
        # Возврат уже создан, осталось поставить статус — идём сразу
        return True
    # Заказ ждёт человека. Перечитываем изредка — чтобы заметить, что он уже
    # всё сделал, и снять уведомление, но не дёргать МойСклад каждые пять минут.
    return not _rechecked_recently(quote)


def sync_orders(*, apply=True):
    """Переносит сведения о доставке Ozon в заказ МойСклада и ставит «Отгружен».

    `apply=False` — только рассказать, что было бы сделано.
    """
    stats = {
        'checked': 0, 'written': 0, 'unchanged': 0, 'missing': 0,
        'shipped': 0, 'by_hand': 0, 'errors': [],
    }

    for quote in _quotes_to_sync():
        postings = sorted(quote.postings_tracked.all(), key=lambda p: p.posting_number)
        block = build_block(quote, postings)
        if not block:
            continue

        stats['checked'] += 1
        text = '\n'.join(block)
        decision = shipping_decision(postings)

        if not _needs_moysklad(quote, note_changed=text != quote.ms_note, decision=decision):
            # Записывали ровно это и решать нечего — в МойСклад не идём вовсе:
            # робот крутится каждые пять минут, а лимит запросов там общий
            # на весь аккаунт.
            stats['unchanged'] += 1
            continue

        try:
            order = ms_client.order_by_external_code(
                quote.site_order_id, params={'expand': 'state,demands'}
            )
        except MoyskladError as exc:
            stats['errors'].append(f'{quote.site_order_id}: {exc}')
            logger.error(
                'Ozon Доставка: заказ сайта %s не прочитать в МойСкладе: %s',
                quote.site_order_id, exc,
            )
            continue

        if order is None:
            # Заказ ещё не завели или черновик сняли — вернёмся на следующем
            # прогоне, но не через пять минут: отметка задаёт паузу.
            stats['missing'] += 1
            logger.info(
                'Ozon Доставка: заказа сайта %s нет в МойСкладе, сведения Ozon не записаны',
                quote.site_order_id,
            )
            OzonDeliveryQuote.objects.filter(pk=quote.pk).update(ms_checked_at=timezone.now())
            continue

        payload = {}
        fields = {'ms_checked_at': timezone.now()}

        description = order.get('description') or ''
        merged = merge_description(description, block)
        if merged != description:
            payload['description'] = merged
        fields['ms_note'] = text

        payload, fields = _decide_shipment(
            quote, order, decision, payload=payload, fields=fields, stats=stats, apply=apply,
        )

        if not apply:
            logger.info(
                'Ozon Доставка: в заказ %s записал бы %s', order.get('name'), payload or '— ничего',
            )
            if payload:
                stats['written'] += 1
            continue

        if payload:
            try:
                ms_client.put(f"/entity/customerorder/{order['id']}", payload)
            except MoyskladError as exc:
                stats['errors'].append(f'{quote.site_order_id}: {exc}')
                logger.error(
                    'Ozon Доставка: заказ %s не обновить: %s', order.get('name'), exc
                )
                continue
            logger.info(
                'Ozon Доставка: заказ МойСклада %s обновлён по заказу Ozon %s (%s)',
                order.get('name'), quote.order_number, ', '.join(payload),
            )
            stats['written'] += 1
        else:
            stats['unchanged'] += 1

        # Отметки ставим и когда менять было нечего: их смысл — «в МойСкладе
        # лежит ровно это», а не «мы это записали».
        OzonDeliveryQuote.objects.filter(pk=quote.pk).update(**fields)

    return stats


def _decide_shipment(quote, order, decision, *, payload, fields, stats, apply=True):
    """Статус «Отгружен»: ставим сами, отдаём человеку или не трогаем вовсе."""
    if decision is None or quote.ms_shipped_at:
        return payload, fields

    if _state_id(order) in HANDS_OFF_STATE_IDS or order.get('demands'):
        # Человек уже отгрузил или отменил заказ — вопрос закрыт без нас,
        # больше к нему не возвращаемся (и уведомление гаснет).
        fields['ms_shipped_at'] = timezone.now()
        logger.info(
            'Ozon Доставка: заказ %s уже закрыт без нас, статус не трогаем',
            order.get('name'),
        )
        return payload, fields

    if decision == SHIP_WITH_RETURN:
        # Посылка уехала со склада Ozon. Тот товар списан ещё при поставке на
        # FBO, поэтому сначала забираем единицу у Озона возвратом — иначе
        # отгрузка покупателю спишет её второй раз.
        postings = sorted(quote.postings_tracked.all(), key=lambda p: p.posting_number)
        try:
            name = ms_returns.ensure_return(quote, postings, apply=apply)
            if apply:
                # Записываем немедленно, отдельным апдейтом: документ в МойСкладе
                # уже есть, и если следующий запрос упадёт, на другом прогоне мы
                # обязаны знать про этот возврат — второй вернул бы товар,
                # которого не было.
                OzonDeliveryQuote.objects.filter(pk=quote.pk).update(ms_return=name)
                quote.ms_return = name
            fields['ms_return'] = name
        except (ms_returns.ReturnNotPossible, MoyskladError) as exc:
            # Статус не ставим: без возврата сценарий создаст отгрузку в минус.
            stats['by_hand'] += 1
            stats['errors'].append(
                f'{quote.site_order_id}: возврат от Озона не создан — '
                f'{ms_returns.return_failed(quote, exc)}'
            )
            logger.error(
                'Ozon Доставка: по заказу %s возврат от Озона не создан: %s',
                order.get('name'), exc,
            )
            return payload, fields

    payload['state'] = {'meta': {
        'href': f'{ms_client.BASE}/entity/customerorder/metadata/states/{SHIPPED_STATE_ID}',
        'type': 'state',
        'mediaType': 'application/json',
    }}
    fields['ms_shipped_at'] = timezone.now()
    stats['shipped'] += 1
    return payload, fields
