"""Сверка заказов сайта с МойСклад: хранилище и сравнение.

Отдельно от 01_reconcile_site_orders.py по двум причинам: имя того файла
начинается с цифры и не импортируется, а сам он тянет api_client, которому нужен
MOYSKLAD_TOKEN — в CI его нет. Здесь только чистая логика, накрытая тестами
(api/tests/test_site_orders_reconcile.py).
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from site_orders_export import SiteOrder

MS_DOC_URL = "https://online.moysklad.ru/app/#customerorder/edit?id="
SITE_ORDER_URL = "https://horse-bio.ru/shop/orders?order_id="

# Заказы старше этой даты заводили руками, и externalCode у них чужой (не номер
# заказа сайта), так что по нему они не находятся вовсе — сверять их бессмысленно,
# получим только ложные «не заведён в МойСклад». Дата — момент первого заказа,
# который завёл робот: МС 06135, 21.07.2026 16:00, externalCode 535513316.
ROBOT_START = "2026-07-21"

# Сколько держим прочитанное. Подтверждённые заказы сайт больше не отдаст,
# так что это хранилище — единственная наша копия; чистим только совсем старое.
KEEP_DAYS = 400

# Расхождение меньше копейки — арифметика с плавающей точкой, а не ошибка
EPS = 0.005

# Размер окна выгрузки. Подтверждаем его ТОЛЬКО когда оно пришло полным, то есть
# когда за ним стоят ещё заказы и иначе до свежих не добраться. Причина: заказ,
# прочитанный неоплаченным, после подтверждения замораживается таким навсегда —
# сайт его больше не отдаст, а покупатель может заплатить и через час. Пока окно
# неполное, мы перечитываем те же заказы каждый прогон и видим их актуальный
# статус оплаты бесплатно. Догоняющие прогоны сами доведут окно до неполного.
WINDOW_SIZE = 500

# Заказы этого дня не сверяем: демон писем ходит по расписанию, и заказ,
# оплаченный за минуту до прогона, ещё не успел попасть в МойСклад — иначе
# каждый прогон выдавал бы ложное «оплачен, но не заведён». Ничего не теряем:
# окно перечитывается, и завтра этот заказ будет проверен.
SETTLE_DAYS = 1

# Сколько дней сверка терпит молчание сайта, прежде чем поднять тревогу.
# Прогон ежедневный, так что двух суток хватает и на разовый сбой, и на то,
# чтобы отличить «сегодня не отдал» от «не отдаёт вообще».
STALE_FETCH_DAYS = 2

EMPTY_STORE = {"orders": {}, "last_fetch": None, "last_acknowledge": None}


def load_store(path: Path) -> dict:
    if not Path(path).exists():
        return dict(EMPTY_STORE, orders={})
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Молча начинать с пустого нельзя: подтверждённые заказы сайт больше не
        # отдаст, и следующее сохранение затёрло бы уцелевший хвост файла.
        raise RuntimeError(
            f"Хранилище заказов сайта повреждено ({path}): {e}. "
            f"Это единственная копия — починить файл вручную, не удалять.") from e


def save_store(path: Path, store: dict) -> None:
    """Пишем рядом и переименовываем: процесс, упавший на середине записи, не
    должен оставить битый файл — второй копии заказов у нас нет."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def prune(store: dict, now: datetime = None) -> int:
    edge = ((now or datetime.now()) - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    # Записи без даты не трогаем: пустая строка меньше любого edge, и они
    # вычищались бы сразу же, хотя это как раз повод разобраться руками.
    stale = [oid for oid, o in store["orders"].items() if o.get("date") and o["date"] < edge]
    for oid in stale:
        del store["orders"][oid]
    return len(stale)


def merge(store: dict, orders: list) -> int:
    """Влить прочитанное окно в хранилище, вернуть число новых заказов."""
    fresh = 0
    for order in orders:
        if order.order_id not in store["orders"]:
            fresh += 1
        store["orders"][order.order_id] = order.as_dict()
    return fresh


def sync_window(export, path: Path, acknowledge: bool, now: datetime = None) -> dict:
    """Прочитать окно выгрузки, сохранить, подтвердить и почистить хранилище.

    Порядок здесь не косметический, каждый шаг стоит на своём месте:

    1. сохраняем прочитанное на диск ДО подтверждения — подтверждение необратимо;
    2. перечитываем файл и убеждаемся, что всё окно в нём есть: если запись не
       долетела (нет прав, не смонтирован том), подтверждать нельзя;
    3. чистим старое ТОЛЬКО после подтверждения. Иначе заказ из окна старше
       KEEP_DAYS вычищался бы тут же, шаг 2 счёл бы его непотерянным, окно не
       подтверждалось бы никогда — и та же самая пятисотка возвращалась бы
       каждый прогон, а свежие заказы не появились бы вовсе.

    Подтверждаем при этом не всегда — только полное окно, см. WINDOW_SIZE.

    export — объект с fetch()/acknowledge() (SiteOrdersExport или его двойник).
    """
    orders = export.fetch()
    refused = getattr(export, "refused", False)

    store = load_store(path)
    fresh = merge(store, orders)
    # last_fetch двигаем только после настоящего ответа: по нему потом считаем,
    # давно ли сайт вообще что-то отдавал
    if not refused:
        store["last_fetch"] = (now or datetime.now()).isoformat(timespec="seconds")
    save_store(path, store)

    ack, lost = None, []
    # Неполное окно значит «мы догнали»: подтверждать нечего и, главное, вредно
    if acknowledge and len(orders) >= WINDOW_SIZE:
        saved = load_store(path)["orders"]
        lost = [o.order_id for o in orders if o.order_id not in saved]
        if not lost:
            ack = export.acknowledge()
            store["last_acknowledge"] = (now or datetime.now()).isoformat(timespec="seconds")

    dropped = prune(store, now=now)
    save_store(path, store)
    return {"fresh": fresh, "window": len(orders), "ack": ack, "lost": lost,
            "dropped": dropped, "refused": refused,
            "stale_days": fetch_age_days(store, now=now)}


def fetch_age_days(store: dict, now: datetime = None) -> int | None:
    """Сколько календарных дней назад была последняя удачная выгрузка
    (None — не было ни разу).

    Считаем именно по датам, а не по прошедшему времени: прогон ежедневный, и
    если он стартует хоть на минуту раньше отметки прошлой выгрузки, разница в
    сутках отбрасывает остаток и теряет целый день — находка о молчании сайта
    вылезала бы на сутки позже, чем задумано.
    """
    last = store.get("last_fetch")
    if not last:
        return None
    return ((now or datetime.now()).date() - datetime.fromisoformat(last).date()).days


def compare(store: dict, ms_index: dict, today: str = None) -> tuple:
    """Сверить сохранённые заказы сайта с заказами МойСклад по externalCode.

    ms_index: {externalCode: строка заказа МойСклад}. Возвращает (находки, сверено).
    Смотрим только оплаченные и не отменённые заказы с ROBOT_START — остальные
    робот заводить и не должен — и не трогаем совсем свежие (см. SETTLE_DAYS).
    """
    missing, sum_mismatch, unpaid = [], [], []
    checked = 0
    settled_before = (
        datetime.fromisoformat(today or datetime.now().strftime("%Y-%m-%d"))
        - timedelta(days=SETTLE_DAYS - 1)
    ).strftime("%Y-%m-%d")

    for raw in sorted(store["orders"].values(), key=lambda o: o.get("date") or ""):
        order = SiteOrder.from_dict(raw)
        if order.date < ROBOT_START or order.cancelled or not order.paid:
            continue
        if order.date >= settled_before:
            continue
        checked += 1

        ms = ms_index.get(order.order_id)
        if ms is None:
            missing.append((order, None))
            continue

        ms_sum = (ms.get("sum") or 0) / 100
        ms_paid = (ms.get("payedSum") or 0) / 100
        if abs(ms_sum - order.total) > EPS:
            sum_mismatch.append((order, ms))
        elif abs(ms_sum - ms_paid) > EPS:
            # Сумма сошлась с сайтом, а оплата нет — платёж провели не на ту сумму
            unpaid.append((order, ms))

    return {"missing": missing, "sum_mismatch": sum_mismatch, "unpaid": unpaid}, checked


def _item(order: SiteOrder, ms: dict, detail: str, severity: str) -> dict:
    return {
        "key": order.order_id,
        "ms_id": (ms or {}).get("id", ""),
        "ms_href": MS_DOC_URL + ms["id"] if ms else SITE_ORDER_URL + order.order_id,
        "object": f"Заказ сайта №{order.number}" + (f" (МС {ms['name']})" if ms else ""),
        "severity": severity,
        "detail": detail,
    }


def build_payload(findings: dict, checked: int, export_error: str = None,
                  stale_days: int = None) -> dict:
    """Структурированный результат для страницы /checks.

    export_error — текст сбоя выгрузки, если сайт не ответил. Его обязательно
    показывать находкой: иначе проверка без доступа к сайту (не прописаны
    SITE_CML_*, протух пароль) молча рисует зелёное «расхождений нет», хотя
    на самом деле не сверила ничего.
    """
    stale = None
    if stale_days is None:
        stale = "выгрузка ни разу не отдала заказы"
    elif stale_days >= STALE_FETCH_DAYS:
        stale = f"последняя удачная выгрузка была {stale_days} дн. назад"

    missing = findings["missing"]
    sum_mismatch = findings["sum_mismatch"]
    unpaid = findings["unpaid"]
    critical = len(missing) + len(sum_mismatch) + (1 if export_error and checked == 0 else 0)
    important = len(unpaid) + (1 if export_error and checked else 0) + (1 if stale else 0)

    categories = []
    if export_error:
        # Нечего было сверять — это отказ проверки, а не её успешное прохождение
        blind = checked == 0
        categories.append({
            "key": "export_down", "title": "Выгрузка заказов с сайта недоступна",
            "severity": "critical" if blind else "important",
            "kind": None, "ms_type": None, "count": 1,
            "note": "Сверка идёт по выгрузке CommerceML с horse-bio.ru. Пока она не отвечает, "
                    "новые заказы не попадают в хранилище" + (
                        " и сверять нечего — проверка не работает." if blind
                        else ", сверка идёт по сохранённой копии и постепенно устаревает.") +
                    " Проверить SITE_CML_URL / SITE_CML_LOGIN / SITE_CML_PASSWORD и доступность сайта.",
            "items": [{"key": "export_down", "ms_id": "", "ms_href": "",
                       "object": "Обмен с сайтом", "severity": "critical" if blind else "important",
                       "detail": export_error}],
        })
    if stale is not None:
        categories.append({
            "key": "export_stale", "title": "Сайт давно не отдаёт заказы",
            "severity": "important", "kind": None, "ms_type": None, "count": 1,
            "note": "Обмен отвечает, но заказов не присылает. Сверка идёт по сохранённой копии и "
                    "не видит новые заказы — то есть тихо устаревает. Проверить в админке сайта "
                    "раздел выгрузки заказов: есть ли заказы со статусом «Не выгружен» и не упёрся "
                    "ли обмен в ограничение частоты.",
            "items": [{"key": "export_stale", "ms_id": "", "ms_href": "",
                       "object": "Обмен с сайтом", "severity": "important",
                       "detail": stale}],
        })
    if missing:
        categories.append({
            "key": "missing", "title": "Оплачен на сайте, но не заведён в МойСклад",
            "severity": "critical", "kind": None, "ms_type": None, "count": len(missing),
            "note": "Покупатель заплатил, а заказа в МойСклад нет — товар не соберут и не отгрузят. "
                    "Обычно это значит, что письмо о заказе не дошло или не разобралось: "
                    "проверить журнал на странице «Заказы сайта».",
            "items": [
                _item(o, None, f"{o.date} · {o.total:.2f} ₽ · {o.status or 'без статуса'}", "critical")
                for o, _ in missing],
        })
    if sum_mismatch:
        categories.append({
            "key": "sum_mismatch", "title": "Сумма заказа разошлась с сайтом",
            "severity": "critical", "kind": None, "ms_type": None, "count": len(sum_mismatch),
            "note": "В МойСклад заказ на одну сумму, а покупатель на сайте заплатил другую. "
                    "Чаще всего это неучтённая скидка: заказ повиснет «частично оплачено», "
                    "а отгрузка по завышенной цене повесит на покупателя несуществующий долг. "
                    "Поправить цены позиций в заказе — и в отгрузке, если она уже создана.",
            "items": [
                _item(o, ms,
                      f"{o.date} · сайт {o.total:.2f} ₽ · МойСклад {(ms.get('sum') or 0) / 100:.2f} ₽ · "
                      f"разница {abs((ms.get('sum') or 0) / 100 - o.total):.2f} ₽"
                      + (f" · скидка сайта {o.discount:.2f} ₽ ({', '.join(o.discount_names)})"
                         if o.discount else ""),
                      "critical")
                for o, ms in sum_mismatch],
        })
    if unpaid:
        categories.append({
            "key": "unpaid", "title": "Оплата не сходится с суммой заказа",
            "severity": "important", "kind": None, "ms_type": None, "count": len(unpaid),
            "note": "Сумма заказа совпала с сайтом, а входящий платёж проведён на другую — "
                    "заказ висит недооплаченным или переплаченным, баланс контрагента врёт. "
                    "Поправить сумму платежа.",
            "items": [
                _item(o, ms,
                      f"{o.date} · заказ {(ms.get('sum') or 0) / 100:.2f} ₽ · "
                      f"оплачено {(ms.get('payedSum') or 0) / 100:.2f} ₽", "important")
                for o, ms in unpaid],
        })

    stats = [
        {"label": "Не заведены в МойСклад", "value": len(missing),
         "tone": "critical" if missing else "ok", **({"cat": "missing"} if missing else {})},
        {"label": "Суммы разошлись", "value": len(sum_mismatch),
         "tone": "critical" if sum_mismatch else "ok", **({"cat": "sum_mismatch"} if sum_mismatch else {})},
        {"label": "Оплата не сходится", "value": len(unpaid),
         "tone": "important" if unpaid else "ok", **({"cat": "unpaid"} if unpaid else {})},
        {"label": "Сверено заказов", "value": checked,
         "tone": "critical" if (export_error and not checked) else "neutral"},
        *([{"label": "Свежесть выгрузки", "value": stale, "tone": "important", "cat": "export_stale"}]
          if stale else []),
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "params": {"since": ROBOT_START},
        "summary": {
            "critical": critical, "important": important, "warnings": 0,
            # Сбой выгрузки в ok не вычитаем: он не про конкретный заказ
            "ok": checked - len(missing) - len(sum_mismatch) - len(unpaid),
            "stats": stats, "view": "snapshot",
            "empty_note": f"Сверено {checked} оплаченных заказов сайта с {ROBOT_START} — "
                          f"все заведены в МойСклад, суммы и оплата сходятся с сайтом.",
        },
        "categories": categories,
    }
