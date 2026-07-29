"""Тесты подсказок города для калькулятора доставки."""

from unittest.mock import patch

from django.test import SimpleTestCase

from api.services.delivery.pec_calculator import suggest_towns


class DeliveryCitySearchTests(SimpleTestCase):
    towns = {
        "Москва": 1,
        "Московский": 2,
        "Санкт-Петербург": 3,
        "Гатчина": 4,
    }

    @patch("api.services.delivery.pec_calculator._load_towns")
    def test_prioritizes_exact_and_prefix_matches(self, load_towns):
        load_towns.return_value = self.towns

        self.assertEqual(
            suggest_towns("Моск"),
            [{"name": "Москва"}, {"name": "Московский"}],
        )

    @patch("api.services.delivery.pec_calculator._load_towns")
    def test_corrects_close_typo(self, load_towns):
        load_towns.return_value = self.towns

        self.assertEqual(suggest_towns("масква")[0], {"name": "Москва"})

    @patch("api.services.delivery.pec_calculator._load_towns")
    def test_does_not_offer_unrelated_text(self, load_towns):
        load_towns.return_value = self.towns

        self.assertEqual(suggest_towns("хуево кукуево"), [])
