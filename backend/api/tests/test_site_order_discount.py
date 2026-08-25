"""Раскладка скидки сайта по позициям заказа (order_email_utils).

Эталоны — живые заказы, по которым 24.08.2026 разбирали инцидент: письмо отдаёт
позиции по РРЦ и total уже со скидкой, а ожидаемые нетто-цены взяты из выгрузки
сайта по CommerceML. Если раскладка разъедется, заказ снова повиснет
«частично оплачено», поэтому цены сверяем до копейки.
"""
import os
import sys

from django.test import SimpleTestCase

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))
from order_email_utils import (  # noqa: E402
    build_discount_label, format_rubles, site_discount_kopecks, split_site_discount,
)


def _goods(items):
    return [
        {"quantity": float(i["quantity"]), "price": round(float(i["price"]) * 100)}
        for i in items
    ]


class SiteDiscountTests(SimpleTestCase):
    # (заказ, позиции письма, доставка, total, ожидаемые цены в рублях)
    REAL_ORDERS = [
        ("07503", [("880", "1")], "428", "1264", [836.0]),
        ("07209", [("4050", "1")], "0", "3442", [3442.0]),
        ("07177", [("3390", "1"), ("3190", "1")], "0", "6251", [3220.5, 3030.5]),
        ("06702", [("4490", "1")], "0", "3816", [3816.0]),
        ("07792", [("3690", "1")], "518", "2708", [2190.0]),
    ]

    def test_real_orders_match_site_prices(self):
        for name, items, delivery_cost, total, expected in self.REAL_ORDERS:
            with self.subTest(order=name):
                items = [{"price": p, "quantity": q} for p, q in items]
                latest = {"items": items, "delivery_cost": delivery_cost, "total": total}
                delivery = {"quantity": 1, "price": round(float(delivery_cost) * 100)}
                total_kopecks = round(float(total) * 100)
                goods = _goods(items)

                applied, unresolved = split_site_discount(goods, delivery, total_kopecks)

                self.assertEqual(unresolved, 0)
                self.assertEqual([g["price"] / 100 for g in goods], expected)
                document = sum(round(g["price"] * g["quantity"]) for g in goods) + delivery["price"]
                self.assertEqual(document, total_kopecks, "сумма заказа обязана сойтись с платежом")
                self.assertEqual(applied, site_discount_kopecks(latest))

    def test_order_without_discount_keeps_prices(self):
        goods = _goods([{"price": "890", "quantity": "2"}])
        applied, unresolved = split_site_discount(goods, {"quantity": 1, "price": 39800}, 217800)
        self.assertEqual((applied, unresolved), (0, 0))
        self.assertEqual([g["price"] for g in goods], [89000])

    def test_kopecks_that_do_not_divide_by_quantity_land_on_single_position(self):
        # 2 × 890 и 1 × 500, скидка 101 ₽ — на пару приходится доля, не кратная 2
        goods = _goods([{"price": "890", "quantity": "2"}, {"price": "500", "quantity": "1"}])
        applied, unresolved = split_site_discount(goods, None, 217900)

        self.assertEqual(unresolved, 0, "остаток обязан осесть на штучной позиции")
        self.assertEqual(applied, 10100)
        self.assertEqual(sum(round(g["price"] * g["quantity"]) for g in goods), 217900)

    def test_discount_larger_than_goods_is_refused(self):
        # total меньше стоимости товаров целиком — предпосылка сломана, цены не трогаем
        goods = _goods([{"price": "1000", "quantity": "1"}])
        applied, unresolved = split_site_discount(goods, None, 0)
        self.assertEqual(applied, 0)
        self.assertEqual(unresolved, 100000)
        self.assertEqual([g["price"] for g in goods], [100000])

    def test_delivery_is_never_discounted(self):
        goods = _goods([{"price": "1000", "quantity": "1"}])
        split_site_discount(goods, {"quantity": 1, "price": 50000}, 140000)
        self.assertEqual(goods[0]["price"], 90000, "скидка 100 ₽ обязана лечь на товар, не на доставку")

    def test_site_discount_kopecks_reads_total_as_truth(self):
        latest = {"items": [{"price": "880", "quantity": "1"}], "delivery_cost": "428", "total": "1264"}
        self.assertEqual(site_discount_kopecks(latest), 4400)
        self.assertEqual(site_discount_kopecks({**latest, "total": ""}), 0)
        self.assertEqual(site_discount_kopecks({**latest, "total": "1308"}), 0)

    def test_residual_splits_a_multi_quantity_line(self):
        # Один товар ×3 и скидка 100 ₽: 2900 / 3 в копейках не делится, и без
        # расщепления заказ разошёлся бы с платежом на копейку
        goods = _goods([{"price": "1000", "quantity": "3"}])

        applied, unresolved = split_site_discount(goods, None, 290000)

        self.assertEqual((applied, unresolved), (10000, 0))
        self.assertEqual(sum(round(g["price"] * g["quantity"]) for g in goods), 290000)
        self.assertEqual([(g["quantity"], g["price"]) for g in goods], [(2.0, 96667), (1, 96666)])

    def test_refused_discount_is_not_announced(self):
        # Если раскладка отказалась работать, комментарий и доп. поле заказа
        # не должны рассказывать о скидке, которой в позициях нет
        latest = {"items": [{"price": "1000", "quantity": "1"}], "delivery_cost": "0", "total": "0"}
        goods = _goods(latest["items"])

        applied, unresolved = split_site_discount(goods, None, 0)

        self.assertEqual((applied, unresolved), (0, 100000))
        self.assertEqual(site_discount_kopecks(latest), 0)

    def test_format_rubles(self):
        self.assertEqual(format_rubles(4400), "44 ₽")
        self.assertEqual(format_rubles(67412), "674,12 ₽")
        self.assertEqual(format_rubles(322050), "3220,5 ₽")


class DiscountLabelTests(SimpleTestCase):
    """Доп. поле «Купон (скидка)» и строка в комментарии заказа."""

    # Тестовый заказ №2074 от 24.08.2026: купон «Кубок Конного парка» на 1500 ₽
    ORDER_2074 = {
        "items": [{"price": "2190", "quantity": "1"}],
        "delivery_cost": "623", "total": "1313",
        "discounts": [{"name": "Кубок Конного парка", "type": "sum",
                       "value": "1500", "is_coupon": True}],
    }

    def test_label_carries_coupon_name_and_amount(self):
        self.assertEqual(build_discount_label(self.ORDER_2074), "Кубок Конного парка, 1500 ₽")

    def test_amount_comes_from_the_difference_not_from_the_coupon_value(self):
        # У процентных скидок сайт не присылает готовую сумму в рублях, поэтому
        # источник — разница позиций и итога, а не value купона
        order = {**self.ORDER_2074,
                 "discounts": [{"name": "Весенняя акция", "type": "percent", "value": "15"}]}
        self.assertEqual(build_discount_label(order), "Весенняя акция, 1500 ₽")

    def test_label_falls_back_to_amount_when_site_sent_no_names(self):
        self.assertEqual(build_discount_label({k: v for k, v in self.ORDER_2074.items()
                                               if k != "discounts"}), "1500 ₽")

    def test_several_discounts_are_listed(self):
        order = {**self.ORDER_2074, "discounts": [{"name": "Купон"}, {"name": "Товарная"}]}
        self.assertEqual(build_discount_label(order), "Купон, Товарная, 1500 ₽")

    def test_order_without_discount_has_no_label(self):
        self.assertEqual(build_discount_label({"items": [{"price": "2190", "quantity": "1"}],
                                               "delivery_cost": "623", "total": "2813"}), "")


class OrderEmailParsingTests(SimpleTestCase):
    """Разбор скрытого блока письма — строки discount_item~~."""

    BLOCK = """<!--HB_ORDER_DATA
Скрытый блок для автоматического заведения заказа в МойСклад по почте.
order_id=4428118
total=1313
discount=1500
delivery_cost=623
item~~05-01VP1000~~ВИТАМИН Е VitaPro, 1000 мл~~1~~2190
discount_item~~Кубок Конного парка~~sum~~1500~~1
HB_ORDER_DATA-->"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        import importlib.util
        path = os.path.join(_HORSEBIO, '01_daemons', '06_order_email_sync', 'scripts',
                            '01_read_order_emails.py')
        spec = importlib.util.spec_from_file_location("read_order_emails", path)
        cls.reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.reader)

    def test_parses_discounts_alongside_items(self):
        data = self.reader.parse_hb_order_data(self.BLOCK)

        self.assertEqual(data["total"], "1313")
        self.assertEqual(data["discount"], "1500")
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["discounts"], [
            {"name": "Кубок Конного парка", "type": "sum", "value": "1500", "is_coupon": True},
        ])

    def test_block_without_discounts_still_parses(self):
        block = "\n".join(line for line in self.BLOCK.splitlines()
                          if not line.startswith("discount_item"))
        data = self.reader.parse_hb_order_data(block)

        self.assertEqual(data["discounts"], [])
        self.assertEqual(build_discount_label({**data, "items": [
            {"price": i["price"], "quantity": i["quantity"]} for i in data["items"]]}), "1500 ₽")
