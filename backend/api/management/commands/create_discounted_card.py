"""Завести карточку уценки и техкарту 1:1 в МойСклад.

Шаг 2 регламента (docs/ucenka.md): по артикулу основного товара создаёт карточку
`Уценка // …` с ценой 70 % от РРЦ и техкарту, которая превращает обычный SKU
в уценённый. Дальше очередь Леры — проставить «Годен до» и провести техоперацию.

    python manage.py create_discounted_card --article 06-04GP1600

Что важно и неочевидно:

* Название через две косые черты — принятый в аккаунте разделитель, а слово
  «Уценка» первым, чтобы его было видно в накладной и в чеке.
* Код карточки — код исходной плюс `-UC`: нумерация в аккаунте ручная,
  автоматический номер МойСклад оставлять нельзя.
* Габариты копируются обязательно, иначе не сформируется накладная СДЭК.
* Группа техкарты задаётся полем `parent`; `productFolder` МойСклад молча
  игнорирует, и техкарта уезжает в корень.
* «Годен до» намеренно не заполняем: дату ставит Лера, увидев упаковку.
"""

import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sync.moysklad import MoySkladAPIClient

BASE_URL = MoySkladAPIClient.BASE_URL
UC_SUFFIX = "-UC"
FOLDER_NAME = "Уценка"
FOLDER_PARENT = "Товары"
PRICE_NAME = "Розница – ИП (Сайт | РРЦ)"
DISCOUNT = 0.7

# Что переносим с основной карточки: габариты нужны СДЭК, остальное — покупателю
COPIED_ATTRIBUTES = {
    "Длина упаковки, см", "Ширина упаковки, см", "Высота упаковки, см",
    "Срок годности", "Условия хранения",
}


class Command(BaseCommand):
    help = "Создать карточку уценки и техкарту 1:1 по артикулу основного товара"

    def add_arguments(self, parser):
        parser.add_argument("--article", required=True, help="артикул основного товара")
        parser.add_argument("--discount", type=float, default=DISCOUNT,
                            help="доля от РРЦ, по умолчанию 0.7 (скидка 30 %%)")

    def handle(self, *args, **options):
        # Клиент отдаёт только авторизацию; на запись МойСклад требует ещё
        # и Content-Type, без него отвечает 1037 «Неверно указан Content-Type»
        self.headers = {**MoySkladAPIClient(settings.MOYSKLAD_TOKEN).headers,
                        "Content-Type": "application/json"}
        article = options["article"]
        uc_article = article + UC_SUFFIX

        if self._get("/entity/product", {"filter": f"article={uc_article}"})["rows"]:
            raise CommandError(f"Карточка {uc_article} уже есть — заводить нечего")

        source = self._get("/entity/product", {"filter": f"article={article}"})["rows"]
        if not source:
            raise CommandError(f"Товар {article} не найден в МойСклад")
        source = source[0]

        product = self._create_product(source, uc_article, options["discount"])
        plan = self._create_plan(source, product)

        self.stdout.write(self.style.SUCCESS(f"Карточка: {product['name']}"))
        self.stdout.write(f"  артикул {product['article']} | код {product.get('code')} | {product.get('pathName')}")
        self.stdout.write(f"  {product['meta']['uuidHref']}")
        self.stdout.write(self.style.SUCCESS(f"Техкарта: {plan['name']}"))
        self.stdout.write(f"  группа {plan.get('pathName') or 'КОРЕНЬ'}")
        self.stdout.write(f"  {plan['meta']['uuidHref']}")
        self.stdout.write("\nДальше: Лера ставит «Годен до» и проводит техоперацию на склад «Уценка»")

    # ── МойСклад ──────────────────────────────────────────────────────────

    def _request(self, method, path, body=None, params=None):
        response = requests.request(
            method, BASE_URL + path, headers=self.headers, params=params,
            data=json.dumps(body, ensure_ascii=False).encode() if body else None, timeout=60,
        )
        if response.status_code >= 300:
            raise CommandError(f"{method} {path}: {response.status_code} {response.text[:400]}")
        return response.json()

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _create_product(self, source, uc_article, discount):
        folders = self._get("/entity/productfolder", {"filter": f"name={FOLDER_NAME}", "limit": 10})["rows"]
        folder = next((f for f in folders if f.get("pathName") == FOLDER_PARENT), None)
        if not folder:
            raise CommandError(f"Группа «{FOLDER_PARENT}/{FOLDER_NAME}» не найдена в МойСклад")

        price_type = next(
            (p for p in self._get("/context/companysettings/pricetype") if p["name"] == PRICE_NAME), None)
        if not price_type:
            raise CommandError(f"Тип цены «{PRICE_NAME}» не найден в МойСклад")
        retail = next(
            (s["value"] for s in source.get("salePrices") or []
             if (s.get("priceType") or {}).get("name") == PRICE_NAME), 0)
        if not retail:
            raise CommandError(f"У товара {source['article']} не заполнена цена «{PRICE_NAME}»")

        payload = {
            "name": f"{FOLDER_NAME} // {source['name']}",
            "article": uc_article,
            "code": (source.get("code") or "") + UC_SUFFIX,
            "productFolder": {"meta": folder["meta"]},
            "uom": source.get("uom"),
            "weight": source.get("weight"),
            "volume": source.get("volume"),
            "vat": source.get("vat"),
            "vatEnabled": source.get("vatEnabled"),
            "effectiveVat": source.get("effectiveVat"),
            "trackingType": source.get("trackingType"),
            "attributes": [{"meta": a["meta"], "value": a["value"]}
                           for a in source.get("attributes") or [] if a["name"] in COPIED_ATTRIBUTES],
            "salePrices": [{"value": round(retail * discount), "priceType": {"meta": price_type["meta"]}}],
        }
        if source.get("country"):
            payload["country"] = {"meta": source["country"]["meta"]}

        return self._request("POST", "/entity/product",
                             {k: v for k, v in payload.items() if v is not None})

    def _create_plan(self, source, product):
        body = {
            "name": product["name"],
            "materials": {"rows": [{"assortment": {"meta": source["meta"]}, "quantity": 1}]},
            "products": {"rows": [{"assortment": {"meta": product["meta"]}, "quantity": 1}]},
        }
        folder = next((f for f in self._get("/entity/processingplanfolder", {"limit": 100})["rows"]
                       if f["name"] == FOLDER_NAME), None)
        if folder:
            # именно parent: productFolder платформа для техкарт игнорирует
            body["parent"] = {"meta": folder["meta"]}
        plan = self._request("POST", "/entity/processingplan", body)
        return self._get(f"/entity/processingplan/{plan['id']}")
