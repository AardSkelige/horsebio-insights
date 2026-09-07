"""Тесты синхронизации остатков уценки с Ozon.

Главное, что здесь проверяется: на витрину Ozon уезжает доступный остаток —
склад минус резерв под уже принятые заказы, — а позиция, которую пора снимать
по сроку, обнуляется. Карточки, которых на Ozon нет, пропускаются молча:
на сайте уценки больше, и это нормальное состояние, а не ошибка.
"""
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import SimpleTestCase

from api.services import ozon_stock
from api.views.discounted import STATE_DELIST, STATE_EXPIRED, STATE_OK

WAREHOUSE = 23996939891000


def _position(article, quantity, reserve=0, state=STATE_OK):
    return {"id": f"id-{article}", "article": article, "name": f"Уценка // {article}",
            "quantity": quantity, "reserve": reserve, "state": state}


class SyncCommandTest(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _run(self, positions, on_ozon, *args):
        out = StringIO()
        with patch("api.management.commands.sync_discounted_ozon.positions_snapshot",
                   return_value=positions), \
             patch.object(ozon_stock, "known_offers", return_value=set(on_ozon)), \
             patch.object(ozon_stock, "warehouse_id", return_value=WAREHOUSE), \
             patch.object(ozon_stock, "push_stock", return_value=[]) as push:
            call_command("sync_discounted_ozon", *args, stdout=out, stderr=out)
        return push, out.getvalue()

    def test_sends_stock_minus_reserve(self):
        """Зарезервированное под принятый заказ продавать второй раз нельзя."""
        push, _ = self._run([_position("A-UC", 40, reserve=2)], ["A-UC"])

        items, warehouse = push.call_args.args
        self.assertEqual(items, [{"offer_id": "A-UC", "stock": 38}])
        self.assertEqual(warehouse, WAREHOUSE)

    def test_zeroes_what_is_due_to_be_delisted(self):
        """Правило регламента: за два месяца до конца срока товар снимается с продажи."""
        push, _ = self._run(
            [_position("A-UC", 10, state=STATE_DELIST), _position("B-UC", 5, state=STATE_EXPIRED)],
            ["A-UC", "B-UC"],
        )

        self.assertEqual(push.call_args.args[0],
                         [{"offer_id": "A-UC", "stock": 0}, {"offer_id": "B-UC", "stock": 0}])

    def test_reserve_over_stock_does_not_send_negative(self):
        """Резерв может обогнать остаток — Ozon отрицательное количество не примет."""
        push, _ = self._run([_position("A-UC", 1, reserve=3)], ["A-UC"])

        self.assertEqual(push.call_args.args[0], [{"offer_id": "A-UC", "stock": 0}])

    def test_skips_cards_absent_on_ozon(self):
        """На сайте уценки больше, чем на Ozon, — это норма, а не повод для ошибки."""
        push, output = self._run(
            [_position("A-UC", 10), _position("B-UC", 4)],
            ["A-UC"],
        )

        self.assertEqual(push.call_args.args[0], [{"offer_id": "A-UC", "stock": 10}])
        self.assertIn("B-UC", output)

    def test_dry_run_sends_nothing(self):
        push, output = self._run([_position("A-UC", 10)], ["A-UC"], "--dry-run")

        push.assert_not_called()
        self.assertIn("A-UC", output)

    def test_no_cards_on_ozon_is_not_an_error(self):
        push, output = self._run([_position("A-UC", 10)], [])

        push.assert_not_called()
        self.assertIn("нет ни одной уценённой карточки", output)


class WarehouseTest(SimpleTestCase):
    """Склад FBS ищется в аккаунте: id — данные, а не константа кода."""

    def test_picks_the_only_active_fbs_warehouse(self):
        warehouses = {"warehouses": [
            {"warehouse_id": WAREHOUSE, "name": "Horse-Bio", "warehouse_type": "fbs", "status": "created"},
            {"warehouse_id": 1, "name": "Тестовый", "warehouse_type": "fbs", "status": "disabled"},
            {"warehouse_id": 2, "name": "РФБС", "warehouse_type": "rfbs", "status": "created"},
        ]}
        with patch.object(ozon_stock, "_post", return_value=warehouses):
            self.assertEqual(ozon_stock.warehouse_id(), WAREHOUSE)

    def test_refuses_to_guess_between_two_active(self):
        warehouses = {"warehouses": [
            {"warehouse_id": 1, "name": "Первый", "warehouse_type": "fbs", "status": "created"},
            {"warehouse_id": 2, "name": "Второй", "warehouse_type": "fbs", "status": "created"},
        ]}
        with patch.object(ozon_stock, "_post", return_value=warehouses):
            with self.assertRaises(ozon_stock.OzonStockError):
                ozon_stock.warehouse_id()


class PushStockTest(SimpleTestCase):
    """Отказ по одной карточке не должен ронять синхронизацию остальных."""

    def test_collects_failures_without_raising(self):
        answer = {"result": [
            {"offer_id": "A-UC", "updated": True, "errors": []},
            {"offer_id": "B-UC", "updated": False,
             "errors": [{"code": "PRODUCT_IS_ARCHIVED", "message": "товар в архиве"}]},
        ]}
        with patch.object(ozon_stock, "_post", return_value=answer):
            failures = ozon_stock.push_stock(
                [{"offer_id": "A-UC", "stock": 5}, {"offer_id": "B-UC", "stock": 1}], WAREHOUSE)

        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "B-UC")
        self.assertIn("PRODUCT_IS_ARCHIVED", failures[0][1])

    def test_splits_into_batches_of_hundred(self):
        """Ozon принимает 100 пар «товар — склад» за запрос."""
        items = [{"offer_id": f"A{i}-UC", "stock": 1} for i in range(150)]
        with patch.object(ozon_stock, "_post", return_value={"result": []}) as post:
            ozon_stock.push_stock(items, WAREHOUSE)

        self.assertEqual(post.call_count, 2)
        self.assertEqual(len(post.call_args_list[0].args[1]["stocks"]), 100)
        self.assertEqual(len(post.call_args_list[1].args[1]["stocks"]), 50)
