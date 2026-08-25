"""
Общие функции для обработки email-заказов сайта horse-bio.ru.

Используется из:
- 01_daemons/06_order_email_sync/scripts/01_read_order_emails.py (чтение почты)
- 01_daemons/06_order_email_sync/scripts/02_create_orders.py (заведение в МойСклад)
- backend/api/views/site_orders.py (страница «Заказы сайта»: список + удаление из журнала)
"""

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def state_lock(state_file: Path):
    """Эксклюзивная блокировка на весь цикл load→process→save state-файла.

    01_read_order_emails.py и 02_create_orders.py — два независимых процесса,
    оба каждые 5 минут читают один и тот же .order_email_state.json, правят
    и переписывают его целиком. Без лока при неудачном стечении времени тот,
    кто сохраняет вторым, затирает файл своей (более старой) копией — и только
    что записанный другим процессом заказ бесследно исчезает, хотя JSON
    остаётся валидным (см. инцидент с заказом 532598916, 21.07.2026). Лок
    держит файл занятым на всё время работы одного процесса — второй просто
    ждёт своей очереди перед чтением.
    """
    state_file.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_file.with_name(state_file.name + ".lock")
    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def load_state(state_file: Path, default: dict) -> dict:
    """Вызывать только внутри state_lock()."""
    if state_file.exists():
        return json.loads(state_file.read_text())
    return dict(default)


def save_state(state_file: Path, state: dict):
    """Пишем во временный файл рядом и атомарно переименовываем (os.replace) —
    так процесс, упавший на середине записи, не оставит битый или пустой JSON.
    Вызывать только внутри state_lock()."""
    tmp_path = state_file.with_name(f"{state_file.name}.tmp-{os.getpid()}")
    tmp_path.write_text(json.dumps(state, indent=2, ensure_ascii=False, default=str))
    os.replace(tmp_path, state_file)


def forget_order(state: dict, order_id: str) -> dict | None:
    """Убрать заказ из журнала: удалить orders[order_id] и вернуть Message-ID его
    писем обратно из processed_message_ids, чтобы при следующей проверке почты
    письмо могло быть разобрано заново. Возвращает удалённый заказ или None, если
    его не было. Схема state принадлежит этому модулю (тут же load_state/save_state),
    поэтому обратная мутация живёт рядом. Вызывать только внутри state_lock()."""
    order = state.get("orders", {}).pop(order_id, None)
    if order is None:
        return None
    processed = state.get("processed_message_ids", [])
    for snap in order.get("history", []):
        mid = snap.get("message_id")
        if mid in processed:
            processed.remove(mid)
    return order


def site_discount_kopecks(latest: dict) -> int:
    """Размер скидки сайта по письму, в копейках (0, если скидки нет).

    В письме позиции идут по РРЦ, а `total` — уже со скидкой. Источник истины
    именно `total`: на эту сумму робот проводит входящий платёж, и ей обязана
    равняться сумма заказа, иначе заказ повиснет «частично оплачено», а отгрузка
    по РРЦ создаст покупателю несуществующий долг (так и было до 24.08.2026).
    Поле `discount` из письма сюда не подмешиваем — оно годится как подпись
    в комментарии, но не как основание для цен.
    """
    total = latest.get("total")
    if total in (None, ""):
        return 0
    goods = sum(
        round(float(item["price"]) * 100) * float(item["quantity"])
        for item in latest.get("items", [])
    )
    delivery = round(float(latest.get("delivery_cost") or 0) * 100)
    discount = round(goods + delivery - round(float(total) * 100))
    if discount <= 0 or discount >= goods:
        # Условие ровно то же, при котором отказывается работать
        # split_site_discount: иначе комментарий и доп. поле заказа рассказывали
        # бы о скидке, которой в позициях нет.
        return 0
    return discount


def split_site_discount(goods: list, delivery: dict, total_kopecks: int) -> tuple:
    """Разложить скидку заказа по товарам, правя `price` позиций на месте.

    Сайт размазывает скидку на заказ по товарам пропорционально их стоимости,
    а доставку под скидку не пускает — сверено с выгрузкой CommerceML на живых
    заказах, совпадает до копейки.

    goods: позиции вида {"quantity": float, "price": int (копейки)}.
    delivery: позиция доставки того же вида либо None. Скидку на неё не кладём,
    но именно её используем как последнее место для копеек, не поделившихся
    на количество (см. ниже).

    Возвращает (разложено_копеек, не_разложено_копеек). Второе число не ноль
    только если скидка не легла ровно — вызывающий код обязан предупредить,
    потому что заказ снова окажется расходящимся с платежом.
    """
    if not goods:
        return 0, 0

    delivery_kopecks = round(delivery["price"] * delivery["quantity"]) if delivery else 0
    lines = [round(p["price"] * p["quantity"]) for p in goods]
    gross_goods = sum(lines)
    discount = gross_goods + delivery_kopecks - total_kopecks
    if discount <= 0:
        return 0, 0
    if discount >= gross_goods:
        # Скидка больше стоимости товаров — предпосылка сломана (частичная
        # предоплата? битый total?). Цены не трогаем, пусть разбирается человек.
        return 0, discount

    # Последней позиции достаётся остаток, чтобы сумма долей сошлась ровно
    shares, left = [], discount
    for line in lines[:-1]:
        share = round(discount * line / gross_goods)
        shares.append(share)
        left -= share
    shares.append(left)

    for position, line, share in zip(goods, lines, shares):
        position["price"] = round((line - share) / position["quantity"])

    # Копейки, не поделившиеся на количество (3 × 966,67 из 2900), должны куда-то
    # деться: расхождение по документу и есть тот самый баг, ради которого всё
    # затевалось. Сначала пробуем штучную позицию — там достаточно поправить цену.
    def _document():
        return sum(round(p["price"] * p["quantity"]) for p in goods) + (
            round(delivery["price"] * delivery["quantity"]) if delivery else 0)

    residual = total_kopecks - _document()
    if residual:
        single = next((p for p in goods if p["quantity"] == 1), None)
        if single is not None:
            single["price"] += residual
        else:
            # Штучной позиции нет — отщепляем одну штуку от самой крупной по
            # количеству и вешаем остаток на неё. В заказе появится вторая строка
            # того же товара с ценой на копейку иной; это заметно глазу, но лучше
            # заказа, который никогда не сойдётся с оплатой.
            biggest = max(goods, key=lambda p: p["quantity"])
            biggest["quantity"] -= 1
            goods.append({**biggest, "quantity": 1, "price": biggest["price"] + residual})
        residual = total_kopecks - _document()
    return discount, residual


def build_discount_label(latest: dict) -> str:
    """Значение доп. поля «Купон (скидка)»: сумма и, если сайт их прислал,
    названия применённых скидок — «Кубок Конного парка, 1500 ₽».

    Сумму берём не из письма, а из разницы позиций и итога (см.
    site_discount_kopecks): у процентных скидок сайт не присылает готовую сумму
    в рублях, а разница есть всегда.
    """
    discount = site_discount_kopecks(latest)
    if not discount:
        return ""
    names = [d["name"].strip() for d in latest.get("discounts", []) if d.get("name", "").strip()]
    return f"{', '.join(names)}, {format_rubles(discount)}" if names else format_rubles(discount)


def build_customer_name(latest: dict) -> str:
    """Собрать ФИО покупателя из полей письма (field:familia/fio/otcestvo)"""
    field = latest.get("field") or {}
    parts = [field.get("familia", "").strip(), field.get("fio", "").strip(), field.get("otcestvo", "").strip()]
    return " ".join(p for p in parts if p)


def format_money(value) -> str:
    """4903 -> '4 903 ₽' — для компактных находок на странице /checks"""
    try:
        n = float(value or 0)
    except (TypeError, ValueError):
        return str(value)
    return f"{n:,.0f}".replace(",", " ") + " ₽"


def format_rubles(kopecks: int) -> str:
    """4400 -> '44 ₽', 67412 -> '674,12 ₽' — точная сумма, в отличие от
    format_money(), который округляет до рубля ради компактности находок."""
    rubles = f"{kopecks / 100:.2f}".rstrip("0").rstrip(".")
    return rubles.replace(".", ",") + " ₽"


def format_phone(raw: str) -> str:
    """+7XXXXXXXXXX -> '+7 999 123-45-67' — для отображения в находках на /checks.
    Формат ввода зеркалит normalize_phone() из 02_create_orders.py, но здесь только
    для человека: если номер нестандартный, просто возвращаем как есть, не роняем."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if len(digits) > 11:
        digits = digits[:11]
    if len(digits) == 11 and digits[0] in ("7", "8"):
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11:
        return f"+{digits[0]} {digits[1:4]} {digits[4:7]}-{digits[7:9]}-{digits[9:11]}"
    return (raw or "").strip()


def build_order_label(latest: dict) -> str:
    """ФИО + номер заказа на сайте — заголовок находки на /checks вместо голого order_id"""
    name = build_customer_name(latest) or "Без имени"
    number = (latest.get("number") or "").strip()
    return f"{name} — №{number}" if number else name


def build_order_delete_action(order_id: str, label: str) -> dict:
    """Данные для кнопки «Удалить» в находке на /checks — убирает запись только
    из нашего журнала (state-файла), письмо и документы в МойСклад не трогает."""
    return {
        "url": f"/site-orders/{order_id}/",
        "confirm": f"Удалить «{label}» из журнала автоматизации? Само письмо и документы "
                   f"в МойСклад (если уже созданы) не тронутся — сотрётся только запись "
                   f"в нашем внутреннем учёте, и при следующей проверке почты письмо "
                   f"может быть разобрано заново.",
    }
