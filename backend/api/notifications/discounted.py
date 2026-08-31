"""Уведомления раздела «Уценка».

Три повода, согласованные с регламентом (docs/ucenka.md):

1. **Пора снимать с продажи** — до конца срока осталось меньше двух месяцев.
   Это не рекомендация, а правило: покупателю нужен месяц на курс и месяц на
   доставку, поэтому такой товар продавать нельзя.
2. **Остаток на сайте разошёлся** — на витрине висит больше, чем лежит на
   складе. При партии в восемь банок это реальный риск продать то, чего нет.
3. **Раскуплено** — на складе ноль, а карточка ещё продаётся.
4. **Не проставлен «Годен до»** — товар на складе есть, а даты в карточке нет.
   Пока её нет, посчитать снятие с продажи не из чего: дата — единственный
   источник срока, МойСклад его не хранит.

Действие в первых трёх случаях одно: выгрузить «Файл для сайта» и загрузить его
в админке. Автоматически ничего не поедет — обмен CommerceML упёрся в демо-лимит
(см. docs/site-channels.md), а файл делает и то, и другое: приводит остаток
к фактическому и убирает с витрины то, что продавать нельзя.

Первые три правила намеренно не пересекаются: действие у них одно, и два
уведомления об одной банке читались бы как шум. Четвёртое стоит отдельно и может
прийти вместе с ними — его действие адресовано другому человеку (дату ставит
Лера в МойСклад), и файл тут ничем не поможет.
"""

from api.views.discounted import (
    STATE_DELIST, STATE_EXPIRED, STATE_NO_DATE, positions_snapshot,
)

from .core import CRITICAL, INFO, WARNING, Notification, provider

# Действие держим в одну строку: подробности («Магазин → Импорт → CSV», какую
# настройку проверить) написаны на самой странице раздела в блоке «Как это
# работает» — повторять их в каждом уведомлении значит утопить в них само дело.
FILE_ACTION = "Выгрузите «Файл для сайта» и загрузите его в админке"


def _short(name):
    """«Уценка // Пробиотик, 1600г» → «Пробиотик, 1600г».

    Слово «Уценка» в названии карточки нужно отделу упаковки, чтобы видеть его
    в накладной. В уведомлении раздела «Уценка» оно только занимает место.
    """
    return name.split("//", 1)[-1].strip() or name


def _links(position):
    links = []
    if position.get("ms_url"):
        links.append(("МойСклад", position["ms_url"]))
    if position.get("published") and position.get("site_url"):
        links.append(("Страница на сайте", position["site_url"]))
    return links


def _delist(position):
    """Пора снимать с продажи — срок вышел или до конца меньше двух месяцев."""
    quantity = int(position["quantity"])
    days_left = position["days_left"]
    if position["state"] == STATE_EXPIRED:
        body = f"Срок вышел {-days_left} дн назад · на складе {quantity} шт"
    else:
        body = f"До конца срока {days_left} дн · на складе {quantity} шт"

    # Если карточки на витрине нет, файл ничего не изменит: остаётся физическая
    # часть регламента — вывести товар со стеллажа и списать.
    if position.get("published") is False:
        action = "Выведите товар со стеллажа и спишите"
    else:
        action = f"{FILE_ACTION} — карточка уйдёт с витрины"

    return Notification(
        key=f"discounted:delist:{position['id']}",
        level=CRITICAL,
        title=f"{_short(position['name'])} — пора снимать с продажи",
        body=body,
        action=action,
        # Дни до конца срока в отпечаток не идут: они меняются каждую ночь,
        # и уведомление становилось бы непрочитанным само собой каждый день
        fingerprint=f"{position['state']}:{position.get('published')}",
        links=_links(position),
    )


def _stock_drift(position):
    """На витрине больше, чем на складе."""
    quantity = int(position["quantity"])
    site_quantity = int(position["site_quantity"])
    return Notification(
        key=f"discounted:stock:{position['id']}",
        level=WARNING,
        title=f"{_short(position['name'])} — остаток на сайте разошёлся",
        body=f"На витрине {site_quantity} шт, на складе {quantity}",
        action=f"{FILE_ACTION} — остаток станет фактическим",
        fingerprint=f"{site_quantity}:{quantity}",
        links=_links(position),
    )


def _sold_out(position):
    """Склад пуст, а карточка продаётся.

    Заголовок намеренно говорит про склад, а не про товар: названия карточек
    разного рода («Подкормка», «Масло», «Пробиотик»), и «раскуплен» рядом
    с половиной из них читается как ошибка.
    """
    site_quantity = position.get("site_quantity")
    body = "Товар раскуплен, карточка на витрине открыта"
    if site_quantity:
        body = f"Товар раскуплен, а на витрине всё ещё {int(site_quantity)} шт"

    return Notification(
        key=f"discounted:sold-out:{position['id']}",
        level=WARNING,
        title=f"{_short(position['name'])} — на складе ноль, а карточка продаётся",
        body=body,
        action=f"{FILE_ACTION} — карточка уйдёт с витрины",
        fingerprint="sold-out",
        links=_links(position),
    )


def _no_date(position):
    """«Годен до» не проставлен, а товар на складе уже лежит.

    Срок годности МойСклад не хранит — дату проставляет человек, и от неё
    считается всё остальное. Пока её нет, позиция вне контроля срока: система
    не знает ни когда её снимать, ни попадает ли она вообще в правила уценки.

    Уровень зависит от того, продаётся ли карточка. Не продаётся — это просто
    ожидание шага 6 регламента, и уведомление информационное. Продаётся — уже
    предупреждение: товар уходит покупателям, а мы не знаем, до какого числа
    его можно отдавать.
    """
    quantity = int(position["quantity"])
    published = position.get("published")

    if published:
        level = WARNING
        body = "Карточка продаётся, а срока нет — непонятно, когда снимать"
    else:
        level = INFO
        body = f"На складе {quantity} шт, срока нет — не посчитать, когда снимать"

    return Notification(
        key=f"discounted:no-date:{position['id']}",
        level=level,
        title=f"{_short(position['name'])} — не проставлен «Годен до»",
        body=body,
        action="Попросите Леру проставить дату в карточке МойСклад",
        # Количество в отпечаток не идёт: оно меняется от каждой продажи,
        # а дела это не меняет — даты по-прежнему нет
        fingerprint=f"no-date:{published}",
        links=_links(position),
    )


@provider("discounted")
def discounted_notifications():
    for position in positions_snapshot():
        quantity = position.get("quantity") or 0
        site_quantity = position.get("site_quantity")

        # Срок и витрина — одна цепочка: действие у всех трёх поводов одно,
        # поэтому сработать должен только первый подошедший
        if quantity > 0 and position["state"] in (STATE_EXPIRED, STATE_DELIST):
            yield _delist(position)
        elif quantity > 0 and site_quantity is not None and site_quantity > quantity:
            yield _stock_drift(position)
        elif quantity == 0 and position.get("published"):
            yield _sold_out(position)

        # Отдельное дело и к другому человеку, поэтому не в цепочке: разъехавшийся
        # остаток правит Сергей файлом, а дату ставит Лера в МойСклад. Заглушить
        # одно другим значило бы потерять одно из двух действий.
        if quantity > 0 and position["state"] == STATE_NO_DATE:
            yield _no_date(position)
