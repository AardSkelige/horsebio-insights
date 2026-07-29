"""Тесты извлечения города из свободного адреса заказа МойСклад."""

from django.test import SimpleTestCase

from api.services.delivery.ms_source import extract_city


class ExtractCityTests(SimpleTestCase):
    def test_skips_country_and_removes_city_prefix(self):
        order = {
            "shipmentAddress": "Россия, г Москва, ул Молодогвардейская, д 33 к 1, помещ 1Ц",
        }

        self.assertEqual(extract_city(order), "Москва")

    def test_country_without_city_is_not_used_as_destination(self):
        self.assertIsNone(extract_city({"shipmentAddress": "Россия"}))

    def test_city_prefix_with_dot_is_removed(self):
        self.assertEqual(
            extract_city({"shipmentAddress": "г. Зеленоград, проспект Центральный"}),
            "Зеленоград",
        )
