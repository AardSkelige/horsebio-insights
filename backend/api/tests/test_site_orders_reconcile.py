"""Сверка заказов сайта с МойСклад: разбор выгрузки и поиск расхождений.

Фикстура XML — урезанная копия живого ответа `type=sale&mode=query` от 24.08.2026
(заказ 2066 / 594131116, скидка «На заказ» 44 ₽). На нём же проверяем главное
свойство выгрузки: ЦенаЗаЕдиницу приходит уже НЕТТО, скидка в неё включена.
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from django.test import SimpleTestCase

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))
sys.path.insert(0, os.path.join(_HORSEBIO, '02_checks', '02_site_orders', 'scripts'))

from site_orders_export import parse_orders  # noqa: E402
import reconcile_core as core  # noqa: E402

SALE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<КоммерческаяИнформация>
  <Документ>
    <Ид>594131116</Ид><Номер>2066</Номер><Сумма>1264</Сумма><Дата>2026-08-19</Дата>
    <Товары>
      <Товар>
        <Наименование>Гель ЮНИФЛЕКС</Наименование><ЦенаЗаЕдиницу>836</ЦенаЗаЕдиницу>
        <Количество>1</Количество><Сумма>836</Сумма><Артикул>01-14AP0250</Артикул>
        <Скидки><Скидка><Наименование>На заказ</Наименование>
          <УчтеноВСумме>true</УчтеноВСумме><Сумма>44</Сумма></Скидка></Скидки>
      </Товар>
      <Товар>
        <Наименование>СДЭК</Наименование><ЦенаЗаЕдиницу>428</ЦенаЗаЕдиницу>
        <Количество>1</Количество><Сумма>428</Сумма>
      </Товар>
    </Товары>
    <ЗначенияРеквизитов>
      <ЗначениеРеквизита><Наименование>Заказ оплачен</Наименование><Значение>true</Значение></ЗначениеРеквизита>
      <ЗначениеРеквизита><Наименование>Отменен</Наименование><Значение>false</Значение></ЗначениеРеквизита>
      <ЗначениеРеквизита><Наименование>Статус заказа</Наименование><Значение>Отработан</Значение></ЗначениеРеквизита>
    </ЗначенияРеквизитов>
  </Документ>
</КоммерческаяИнформация>"""


def _ms(sum_rub, payed_rub, name="07503"):
    return {"id": "ms-uuid", "name": name,
            "sum": round(sum_rub * 100), "payedSum": round(payed_rub * 100)}


def _store(orders):
    return {"orders": {o.order_id: o.as_dict() for o in orders}}


def _full_window(order, size=None):
    """Копии заказа с разными Ид — окно ровно того размера, при котором
    sync_window считает, что за ним стоят ещё заказы."""
    size = size or core.WINDOW_SIZE
    window = []
    for i in range(size):
        clone = core.SiteOrder.from_dict(order.as_dict())
        clone.order_id = f"{order.order_id}-{i}"
        window.append(clone)
    return window


TODAY = "2026-08-25"   # фиксируем «сегодня»: сверка не трогает свежие заказы


class SiteOrdersExportParseTests(SimpleTestCase):
    def test_parses_order_with_discount(self):
        order = parse_orders(SALE_XML)[0]

        self.assertEqual((order.order_id, order.number, order.date), ("594131116", "2066", "2026-08-19"))
        self.assertEqual(order.total, 1264.0)
        self.assertTrue(order.paid)
        self.assertFalse(order.cancelled)
        self.assertEqual(order.status, "Отработан")
        self.assertEqual(order.discount, 44.0)
        self.assertEqual(order.discount_names, ["На заказ"])

    def test_price_is_net_and_delivery_is_recognised(self):
        goods, delivery = parse_orders(SALE_XML)[0].positions

        self.assertFalse(goods.is_delivery)
        self.assertEqual(goods.price, 836.0, "ЦенаЗаЕдиницу приходит уже со скидкой")
        self.assertTrue(delivery.is_delivery, "у доставки нет артикула — это услуга")
        self.assertEqual(delivery.discounts, [], "на доставку скидка не распространяется")

    def test_refused_status_counts_as_cancelled(self):
        # Реквизит «Отменен» на живой выгрузке не выставлен ни у одного заказа,
        # отказ виден только в статусе — иначе оплаченный и отменённый заказ
        # попал бы в находки как «не заведён в МойСклад»
        refused = SALE_XML.replace("<Значение>Отработан</Значение>", "<Значение>Отказ</Значение>")
        order = parse_orders(refused)[0]

        self.assertTrue(order.cancelled)
        findings, checked = core.compare(_store([order]), {}, today=TODAY)
        self.assertEqual((checked, findings["missing"]), (0, []))

    def test_survives_roundtrip_through_store(self):
        order = parse_orders(SALE_XML)[0]
        restored = core.SiteOrder.from_dict(json.loads(json.dumps(order.as_dict())))
        self.assertEqual(restored.as_dict(), order.as_dict())


class ReconcileTests(SimpleTestCase):
    def setUp(self):
        self.order = parse_orders(SALE_XML)[0]

    def test_matching_order_produces_no_findings(self):
        findings, checked = core.compare(_store([self.order]), {"594131116": _ms(1264, 1264)}, today=TODAY)

        self.assertEqual(checked, 1)
        self.assertEqual([k for k, v in findings.items() if v], [])

    def test_unaccounted_discount_is_critical(self):
        # Так выглядел заказ 07503 до починки: в МойСклад РРЦ 1308, а списано 1264
        findings, _ = core.compare(_store([self.order]), {"594131116": _ms(1308, 1264)}, today=TODAY)

        self.assertEqual(len(findings["sum_mismatch"]), 1)
        payload = core.build_payload(findings, 1)
        self.assertEqual(payload["summary"]["critical"], 1)
        detail = payload["categories"][0]["items"][0]["detail"]
        self.assertIn("разница 44.00 ₽", detail)
        self.assertIn("На заказ", detail)

    def test_missing_order_is_critical(self):
        findings, checked = core.compare(_store([self.order]), {}, today=TODAY)

        self.assertEqual(checked, 1)
        self.assertEqual(len(findings["missing"]), 1)
        payload = core.build_payload(findings, 1)
        self.assertEqual(payload["categories"][0]["key"], "missing")
        # Ссылка ведёт на сайт: документа в МойСклад ещё нет
        self.assertTrue(payload["categories"][0]["items"][0]["ms_href"].startswith(core.SITE_ORDER_URL))

    def test_payment_on_wrong_sum_is_important(self):
        findings, _ = core.compare(_store([self.order]), {"594131116": _ms(1264, 1000)}, today=TODAY)

        self.assertEqual(len(findings["unpaid"]), 1)
        self.assertEqual(core.build_payload(findings, 1)["summary"]["important"], 1)

    def test_orders_before_robot_are_skipped(self):
        # До ROBOT_START заказы заводили руками и с чужим externalCode — по нему
        # они не находятся, и без отсечки давали бы ложное «не заведён»
        self.order.date = "2026-07-20"
        findings, checked = core.compare(_store([self.order]), {}, today=TODAY)

        self.assertEqual(checked, 0)
        self.assertEqual(findings["missing"], [])

    def test_unpaid_and_cancelled_orders_are_skipped(self):
        for attr in ("paid", "cancelled"):
            with self.subTest(attr=attr):
                setattr(self.order, attr, attr == "cancelled")
                findings, checked = core.compare(_store([self.order]), {}, today=TODAY)
                self.assertEqual(checked, 0)
                self.assertEqual(findings["missing"], [])

    def test_today_orders_are_left_alone(self):
        # Демон писем ходит по расписанию: заказ, оплаченный за минуту до прогона,
        # ещё не успел попасть в МойСклад, и ругаться на него — ложная тревога
        self.order.date = TODAY
        findings, checked = core.compare(_store([self.order]), {}, today=TODAY)

        self.assertEqual((checked, findings["missing"]), (0, []))

    def test_kopeck_noise_is_not_a_finding(self):
        findings, _ = core.compare(_store([self.order]), {"594131116": _ms(1264.001, 1264.001)}, today=TODAY)
        self.assertEqual([k for k, v in findings.items() if v], [])


class FakeExport:
    """Двойник SiteOrdersExport: отдаёт заданное окно и считает подтверждения."""

    def __init__(self, orders):
        self.orders = orders
        self.acknowledged = 0

    def fetch(self):
        return self.orders

    def acknowledge(self):
        self.acknowledged += 1
        return "success"


class SyncWindowTests(SimpleTestCase):
    def setUp(self):
        self.order = parse_orders(SALE_XML)[0]

    def _run(self, tmp, **kwargs):
        return core.sync_window(self.export, Path(tmp) / "store.json", **kwargs)

    def test_incomplete_window_is_not_acknowledged(self):
        # Окно не полное — значит мы догнали, и за ним ничего не стоит.
        # Подтверждать нельзя: заказ, прочитанный неоплаченным, замёрзнет таким
        # навсегда, а покупатель ещё может заплатить.
        self.export = FakeExport([self.order])

        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp, acknowledge=True)

        self.assertEqual(self.export.acknowledged, 0)
        self.assertIsNone(result["ack"])

    def test_old_order_in_window_does_not_block_acknowledgement(self):
        # Окно выгрузки начинается в 2025 году: если чистить хранилище ДО
        # подтверждения, заказ старше KEEP_DAYS вычищается сразу, проверка
        # «всё ли сохранилось» считает его потерянным, и окно не подтверждается
        # никогда — та же пятисотка возвращается каждый прогон, свежих заказов
        # не видно вовсе.
        self.order.date = "2024-01-01"
        self.export = FakeExport(_full_window(self.order))

        with tempfile.TemporaryDirectory() as tmp:
            result = self._run(tmp, acknowledge=True, now=datetime(2026, 9, 30))

        self.assertEqual(result["lost"], [], "старый заказ — не признак несохранённой записи")
        self.assertEqual(self.export.acknowledged, 1, "полное окно обязано подтвердиться")
        self.assertEqual(result["dropped"], core.WINDOW_SIZE, "и только потом чистка")

    def test_acknowledges_and_stores_full_window(self):
        self.export = FakeExport(_full_window(self.order))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            result = core.sync_window(self.export, path, acknowledge=True)

            self.assertEqual((result["fresh"], result["window"]),
                             (core.WINDOW_SIZE, core.WINDOW_SIZE))
            self.assertEqual(self.export.acknowledged, 1)
            store = core.load_store(path)
            self.assertIn("594131116-0", store["orders"])
            self.assertIsNotNone(store["last_acknowledge"])

    def test_does_not_acknowledge_when_asked_not_to(self):
        self.export = FakeExport([self.order])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            core.sync_window(self.export, path, acknowledge=False)

            self.assertEqual(self.export.acknowledged, 0)
            self.assertIn("594131116", core.load_store(path)["orders"])

    def test_does_not_acknowledge_when_store_did_not_persist(self):
        self.export = FakeExport(_full_window(self.order))

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "store.json"
            # имитируем не долетевшую запись: файл исчез между save и перечиткой
            original = core.save_store
            core.save_store = lambda *a, **kw: None
            try:
                result = core.sync_window(self.export, path, acknowledge=True)
            finally:
                core.save_store = original

        self.assertEqual(len(result["lost"]), core.WINDOW_SIZE)
        self.assertEqual(self.export.acknowledged, 0, "без копии на диске подтверждать нельзя")


class ExportFailureTests(SimpleTestCase):
    """Недоступная выгрузка не должна выглядеть как успешно пройденная проверка."""

    EMPTY = {"missing": [], "sum_mismatch": [], "unpaid": []}

    def test_failure_without_stored_copy_is_critical(self):
        payload = core.build_payload(self.EMPTY, 0, export_error="Сайт недоступен (query): timeout")

        self.assertEqual(payload["summary"]["critical"], 1)
        self.assertEqual(payload["categories"][0]["key"], "export_down")
        self.assertIn("timeout", payload["categories"][0]["items"][0]["detail"])

    def test_failure_with_stored_copy_is_only_important(self):
        payload = core.build_payload(self.EMPTY, 12, export_error="Сайт недоступен (query): timeout")

        self.assertEqual((payload["summary"]["critical"], payload["summary"]["important"]), (0, 1))
        self.assertEqual(payload["categories"][0]["severity"], "important")

    def test_healthy_run_reports_no_export_category(self):
        payload = core.build_payload(self.EMPTY, 12)

        self.assertEqual(payload["categories"], [])
        self.assertEqual(payload["summary"]["ok"], 12)


class StoreTests(SimpleTestCase):
    def test_merge_counts_only_new_orders(self):
        order = parse_orders(SALE_XML)[0]
        store = dict(core.EMPTY_STORE, orders={})

        self.assertEqual(core.merge(store, [order]), 1)
        self.assertEqual(core.merge(store, [order]), 0, "повторное окно новых заказов не добавляет")

    def test_prune_drops_only_ancient_orders(self):
        order = parse_orders(SALE_XML)[0]
        store = dict(core.EMPTY_STORE, orders={})
        core.merge(store, [order])

        self.assertEqual(core.prune(store, now=datetime(2026, 9, 1)), 0)
        self.assertEqual(core.prune(store, now=datetime(2030, 1, 1)), 1)
        self.assertEqual(store["orders"], {})

    def test_save_is_atomic_and_roundtrips(self):
        order = parse_orders(SALE_XML)[0]
        store = dict(core.EMPTY_STORE, orders={})
        core.merge(store, [order])

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "site_orders.json"
            core.save_store(path, store)

            self.assertEqual(core.load_store(path), store)
            self.assertEqual(list(path.parent.glob("*.tmp-*")), [], "временный файл не должен оставаться")

    def test_orders_without_date_survive_pruning(self):
        store = {"orders": {"X": {"order_id": "X", "date": ""}}}
        self.assertEqual(core.prune(store, now=datetime(2030, 1, 1)), 0,
                         "запись без даты — повод разобраться руками, а не вычистить")

    def test_corrupt_store_raises_instead_of_resetting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "site_orders.json"
            path.write_text('{"orders": {"X": ', encoding="utf-8")

            with self.assertRaises(RuntimeError) as ctx:
                core.load_store(path)
            self.assertIn("повреждено", str(ctx.exception))

    def test_load_missing_file_gives_empty_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(core.load_store(Path(tmp) / "нет.json")["orders"], {})
