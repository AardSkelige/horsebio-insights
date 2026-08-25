"""Выгрузка заказов сайта horse-bio.ru по CommerceML (type=sale).

Зачем отдельный модуль: письма о заказах не передают скидку — позиции в них идут
по РРЦ, а итог уже со скидкой (см. site_discount_kopecks в order_email_utils).
Выгрузка же отдаёт цены нетто и сами скидки с названиями, поэтому годится как
независимый источник для сверки того, что робот завёл в МойСклад.

Что важно знать (проверено на живом сайте 24.08.2026):

* `mode=query` отдаёт 500 САМЫХ СТАРЫХ неподтверждённых заказов. Пагинации и
  фильтра по дате нет — перебрал from/fromdate/offset/limit/page/id, все
  игнорируются. Пока окно не сдвинешь, свежих заказов не увидишь.
* Сдвигает окно только `mode=success`, и он необратим: подтверждённый заказ
  исчезает из выгрузки навсегда. Поэтому порядок строго такой — прочитать,
  сохранить к себе на диск, и только потом подтверждать.
* `ЦенаЗаЕдиницу` — всегда цена НЕТТО, скидка в неё уже включена. Рядом лежит
  `<Скидки>` с названием и суммой: «На заказ» (скидка на заказ, размазанная по
  товарам), «Купон» (фиксированная сумма) и «Товарная» (процент на товар); они
  складываются друг с другом. У «Купона» стоит `УчтеноВСумме=false`, но цена всё
  равно нетто — флагу не верить, сверено арифметикой с РРЦ в МойСклад.
* На доставку скидка не распространяется, у позиции доставки нет артикула.
* В выгрузку попадают только заказы, ушедшие из статуса «Новый»: в окне из 500
  заказов за год не встретилось ни одного «Нового» (415 «Отработан», 14 «В
  работе», 71 «Отказ»). То есть сверка видит заказ не сразу, а когда менеджер
  или сайт переведут его дальше по воронке.
* Когда подтверждать нечего, сайт отвечает не пустым XML, а JSON-ошибкой
  `{"error":{"message":"Bad Request","code":400}}` — причём с HTTP 200. Это
  нормальная «очередь пуста», а не сбой (проверено 25.08.2026 сразу после
  mode=success).
* Megagroup узнаёт себя по User-Agent 1С — с обычным заголовком обмен не отвечает.
"""

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import requests

USER_AGENT = "1C+Enterprise/8.3"
TIMEOUT = 120

# Статус отказа сайт держит только в «Статус заказа»: реквизит «Отменен» на живой
# выгрузке не выставлен ни у одного из 500 заказов. Статусов в магазине четыре —
# «Новый», «В работе», «Отработан», «Отказ», — но менеджер их почти не
# проставляет, и за год в выгрузке встретились только три: «Отработан»
# (415), «В работе» (14) и «Отказ» (71). Отменяющий среди них один, и все 71
# «Отказ» неоплачены. Если появится ещё один отменяющий статус — дописать сюда,
# иначе оплаченный и отменённый заказ попадёт в находки как «не заведён».
CANCELLED_STATUSES = {"Отказ"}


class SiteExportError(Exception):
    """Выгрузка заказов не удалась."""


@dataclass
class SiteDiscount:
    name: str
    amount: float


@dataclass
class SitePosition:
    article: str          # пусто у доставки — это услуга, а не товар
    name: str
    price: float          # за единицу, уже со скидкой
    quantity: float
    total: float
    discounts: list = field(default_factory=list)

    @property
    def is_delivery(self) -> bool:
        return not self.article


@dataclass
class SiteOrder:
    order_id: str
    number: str
    date: str
    total: float          # итог заказа, уже со скидкой
    paid: bool
    cancelled: bool
    status: str
    positions: list = field(default_factory=list)

    @property
    def discount(self) -> float:
        return round(sum(d.amount for p in self.positions for d in p.discounts), 2)

    @property
    def discount_names(self) -> list:
        seen = []
        for position in self.positions:
            for discount in position.discounts:
                if discount.name not in seen:
                    seen.append(discount.name)
        return seen

    def as_dict(self) -> dict:
        return {
            "order_id": self.order_id, "number": self.number, "date": self.date,
            "total": self.total, "paid": self.paid, "cancelled": self.cancelled,
            "status": self.status,
            "positions": [
                {"article": p.article, "name": p.name, "price": p.price,
                 "quantity": p.quantity, "total": p.total,
                 "discounts": [{"name": d.name, "amount": d.amount} for d in p.discounts]}
                for p in self.positions
            ],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "SiteOrder":
        return cls(
            order_id=raw["order_id"], number=raw["number"], date=raw["date"],
            total=raw["total"], paid=raw["paid"], cancelled=raw["cancelled"],
            status=raw["status"],
            positions=[
                SitePosition(
                    article=p["article"], name=p["name"], price=p["price"],
                    quantity=p["quantity"], total=p["total"],
                    discounts=[SiteDiscount(d["name"], d["amount"]) for d in p["discounts"]],
                )
                for p in raw["positions"]
            ],
        )


def _text(node, path, default=""):
    found = node.find(path)
    return found.text if found is not None and found.text is not None else default


def _number(node, path, default=0.0) -> float:
    try:
        return float(_text(node, path) or default)
    except ValueError:
        return default


def _requisites(node) -> dict:
    return {
        _text(r, "Наименование"): _text(r, "Значение")
        for r in node.findall("./ЗначенияРеквизитов/ЗначениеРеквизита")
    }


def parse_orders(xml: str) -> list:
    """Разобрать XML выгрузки в список SiteOrder."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise SiteExportError(f"Сайт вернул не XML: {e}") from e

    orders = []
    for node in root.findall(".//Документ"):
        requisites = _requisites(node)
        positions = []
        for item in node.findall("./Товары/Товар"):
            positions.append(SitePosition(
                article=_text(item, "Артикул"),
                name=_text(item, "Наименование"),
                price=_number(item, "ЦенаЗаЕдиницу"),
                quantity=_number(item, "Количество"),
                total=_number(item, "Сумма"),
                discounts=[
                    SiteDiscount(name=_text(d, "Наименование"), amount=_number(d, "Сумма"))
                    for d in item.findall("./Скидки/Скидка")
                ],
            ))
        orders.append(SiteOrder(
            order_id=_text(node, "Ид"),
            number=_text(node, "Номер"),
            date=_text(node, "Дата"),
            total=_number(node, "Сумма"),
            paid=requisites.get("Заказ оплачен") == "true",
            cancelled=(requisites.get("Отменен") == "true"
                       or requisites.get("Статус заказа", "") in CANCELLED_STATUSES),
            status=requisites.get("Статус заказа", ""),
            positions=positions,
        ))
    return orders


class SiteOrdersExport:
    """Сессия обмена с сайтом. Читает заказы и (по отдельной команде) подтверждает."""

    def __init__(self, url: str = None, login: str = None, password: str = None):
        self.url = url or os.getenv("SITE_CML_URL", "https://horse-bio.ru/-/api/cml/v2/")
        login = login or os.getenv("SITE_CML_LOGIN")
        password = password or os.getenv("SITE_CML_PASSWORD")
        if not (login and password):
            raise SiteExportError("Не заданы SITE_CML_LOGIN и SITE_CML_PASSWORD")
        self.session = requests.Session()
        self.session.auth = (login, password)
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._authenticated = False

    def _request(self, mode: str):
        """Любой сбой сети — тоже SiteExportError: вызывающий обязан уметь
        пережить лежащий сайт и свериться по сохранённой копии."""
        try:
            return self.session.get(
                self.url, params={"type": "sale", "mode": mode}, timeout=TIMEOUT)
        except requests.RequestException as e:
            raise SiteExportError(f"Сайт недоступен ({mode}): {e}") from e

    def _authenticate(self) -> None:
        response = self._request("checkauth")
        if response.status_code != 200 or not response.text.startswith("success"):
            raise SiteExportError(f"Сайт не принял авторизацию: {response.text[:200]}")
        # Ответ checkauth — три строки: success, имя cookie, её значение. Без этой
        # cookie сайт не свяжет последующие запросы в один обмен.
        lines = response.text.splitlines()
        if len(lines) >= 3:
            self.session.cookies.set(lines[1].strip(), lines[2].strip())
        self._authenticated = True

    def fetch(self) -> list:
        """Прочитать окно заказов. Ничего на сайте не меняет."""
        if not self._authenticated:
            self._authenticate()
        response = self._request("query")
        if response.status_code != 200:
            raise SiteExportError(f"Выгрузка вернула {response.status_code}: {response.text[:200]}")
        body = response.text.lstrip("\ufeff").lstrip()
        if not body.startswith("<"):
            # Пустая очередь приходит как JSON-ошибка, а не как пустой документ.
            # Отличить её от настоящего Bad Request по телу нельзя, но checkauth
            # выше уже прошёл — значит и адрес, и логин с паролем в порядке,
            # и другого смысла у этого ответа не остаётся.
            return []
        return parse_orders(body)

    def acknowledge(self) -> str:
        """Подтвердить прочитанное окно — НЕОБРАТИМО: эти заказы больше никогда
        не придут в выгрузке. Вызывать только после того, как они сохранены."""
        if not self._authenticated:
            raise SiteExportError("acknowledge() до fetch() — подтверждать нечего")
        response = self._request("success")
        if response.status_code != 200:
            raise SiteExportError(f"Подтверждение вернуло {response.status_code}: {response.text[:200]}")
        return response.text.strip()
