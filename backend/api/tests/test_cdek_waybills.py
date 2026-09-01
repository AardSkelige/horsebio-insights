"""Накладные СДЭК: как робот определяет способ доставки и адрес получателя.

Сайт способ доставки не передаёт (в письме о заказе всегда просто «СДЭК»), поэтому
робот читает его из адреса и текста заказа. Здесь закреплено поведение, на котором
он споткнулся на заказе 08235 (01.09.2026): адрес пункта выдачи вписан словами, без
кода — робот молча оформил курьера, а СДЭК не распознал «Мневники» без «ё».
"""
import os
import sys

from django.test import SimpleTestCase

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '01_daemons', '07_cdek_waybills', 'scripts'))

import waybill_rules as rules  # noqa: E402

PACKAGE = {"weight": 1375, "length": 20, "width": 20, "height": 30}


def cdek_location_error(to_location, packages):
    """Калькулятор СДЭК: распознаёт локацию, только если город задан отдельно.

    Так ведёт себя живой API — строку целиком он геокодит буквально (проверено
    01.09.2026: «Москва, ул. Мневники, 23» → v2_recipient_location_not_recognized,
    та же улица с городом отдельным полем → 46 тарифов)."""
    if to_location.get("city") or to_location.get("postal_code"):
        return None
    return "Recipient location is not recognized"


def resolve(address, order_text=""):
    return rules.resolve_delivery(address, order_text, PACKAGE, cdek_location_error)


class DeliveryModeTests(SimpleTestCase):
    def test_pvz_code_in_address_goes_to_pickup_point(self):
        self.assertEqual(
            resolve("PTG11, Пятигорск, ул. Юлиуса Фучика (357524, Россия)",
                    "Способ доставки: СДЭК"),
            ("pvz", "PTG11"))

    def test_no_pvz_mention_goes_to_courier(self):
        kind, to_location = resolve("121552, Россия, г Москва, ул Ярцевская, д 31, кв 104",
                                    "Способ доставки: СДЭК")
        self.assertEqual(kind, "courier")
        self.assertEqual(to_location["postal_code"], "121552")

    def test_pickup_point_without_code_is_blocked_not_shipped_by_courier(self):
        """Заказ 08235: «СДЭК ПВЗ» + адрес пункта словами — курьера слать нельзя."""
        kind, reason = resolve("Москва, ул. Мневники, 23", "СДЭК ПВЗ")
        self.assertEqual(kind, "blocked")
        self.assertIn("код", reason)

    def test_pickup_point_spelled_out_is_recognized(self):
        self.assertEqual(resolve("Москва, ул. Мневники, 23",
                                 "Способ доставки: СДЭК Пункт выдачи")[0], "blocked")

    def test_unrecognized_address_is_blocked_with_cdek_reason(self):
        kind, reason = resolve("Балашиха", "Способ доставки: СДЭК")
        self.assertEqual(kind, "blocked")
        self.assertIn("не распознал адрес", reason)


class DeliveryTextTests(SimpleTestCase):
    def test_own_reason_line_does_not_look_like_pickup_choice(self):
        """Причина, записанная роботом, содержит «ПВЗ» — но это не выбор способа:
        иначе заказ остался бы заблокированным и после правки менеджера."""
        order = {
            "description": (f"СДЭК КУРЬЕР\n{rules.REASON_MARKER_PREFIX} "
                            f"{rules.PVZ_WITHOUT_CODE_REASON}"),
            "shipmentAddressFull": {"comment": ""},
        }
        text = rules.delivery_text(order)
        self.assertNotIn("ПВЗ", text)
        self.assertEqual(resolve("121552, Россия, г Москва, ул Ярцевская, д 31", text)[0],
                         "courier")

    def test_manager_note_in_address_comment_is_read(self):
        order = {"description": "", "shipmentAddressFull": {"comment": "СДЭК ПВЗ"}}
        self.assertIn("ПВЗ", rules.delivery_text(order))


class AddressParsingTests(SimpleTestCase):
    """Город (или индекс) отдаём СДЭК отдельным полем — тогда опечатка в улице
    («Мневники» вместо «Мнёвники») перестаёт быть фатальной."""

    def test_postal_code_and_city_come_before_raw_string(self):
        got = rules.to_location_candidates('121353, Россия, г Москва, ул Беловежская, д 39')
        self.assertEqual(got[0]["postal_code"], "121353")
        self.assertEqual(got[1]["city"], "Москва")
        self.assertEqual(got[-1], {"address": "121353, Россия, г Москва, ул Беловежская, д 39"})

    def test_city_prefix_is_stripped(self):
        self.assertEqual(rules.to_location_candidates("г. Ижевск, ул. Пушкинская, 290")[0],
                         {"city": "Ижевск", "address": "ул. Пушкинская, 290"})

    def test_address_without_street_stays_whole(self):
        self.assertEqual(rules.to_location_candidates("г. Балашиха"),
                         [{"address": "г. Балашиха"}])
