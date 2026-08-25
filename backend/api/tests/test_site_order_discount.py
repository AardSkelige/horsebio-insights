"""Раскладка скидки сайта по позициям заказа (order_email_utils).

Эталоны — живые заказы, по которым 24.08.2026 разбирали инцидент: письмо отдаёт
позиции по РРЦ и total уже со скидкой, а ожидаемые нетто-цены взяты из выгрузки
сайта по CommerceML. Если раскладка разъедется, заказ снова повиснет
«частично оплачено», поэтому цены сверяем до копейки.
"""
import os
import sys

from django.test import SimpleTestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio', '_shared'))
from order_email_utils import (  # noqa: E402
    format_rubles, site_discount_kopecks, split_site_discount,
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
