"""Накладные СДЭК: как робот определяет способ доставки и адрес получателя.

Сайт способ доставки не передаёт (в письме о заказе всегда просто «СДЭК»), поэтому
робот читает его из адреса и текста заказа. Здесь закреплено поведение, на котором
он споткнулся на заказе 08235 (01.09.2026): адрес пункта выдачи вписан словами, без
кода — робот молча оформил курьера, а СДЭК не распознал «Мневники» без «ё».
"""
import importlib.util
import os
import sys

from django.test import SimpleTestCase

_HORSEBIO = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio')
sys.path.insert(0, os.path.join(_HORSEBIO, '_shared'))

_SCRIPT = os.path.join(_HORSEBIO, '01_daemons', '07_cdek_waybills', 'scripts',
                       '01_create_waybills.py')
_spec = importlib.util.spec_from_file_location('cdek_waybills', _SCRIPT)
waybills = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(waybills)


class FakeCdek:
    """Калькулятор СДЭК: распознаёт локацию, только если город задан отдельно.

    Так ведёт себя живой API — строку целиком он геокодит буквально (проверено
    01.09.2026: «Москва, ул. Мневники, 23» → v2_recipient_location_not_recognized,
    та же улица с городом отдельным полем → 46 тарифов)."""

    def location_error(self, to_location, packages, from_code=None):
        if to_location.get('city') or to_location.get('postal_code'):
            return None
        return 'Recipient location is not recognized'


class FakeMs:
    def _get(self, path, params=None):
        return {'rows': []}


def make_order(address, description='', comment=''):
    return {
        'id': 'order-id',
        'name': '08235',
        'description': description,
        'payedSum': 795000.0,
        'shipmentAddressFull': {'addInfo': address, 'comment': comment},
        'agent': {'name': 'Покупатель', 'phone': '+79852759792'},
        'positions': {'rows': [{
            'quantity': 1.0,
            'price': 795000.0,
            'assortment': {
                'meta': {'type': 'product'},
                'name': 'Хондропротектор',
                'article': '11-24AP1200',
                'weight': 1375.0,
                'attributes': [
                    {'id': waybills.ATTR_LENGTH_ID, 'value': 20},
                    {'id': waybills.ATTR_WIDTH_ID, 'value': 20},
                    {'id': waybills.ATTR_HEIGHT_ID, 'value': 30},
                ],
            },
        }]},
    }


class DeliveryModeTests(SimpleTestCase):
    def setUp(self):
        self.creator = waybills.WaybillCreator(FakeMs(), FakeCdek())
        self.creator.state = {'orders': {}}

    def test_pvz_code_in_address_goes_to_pickup_point(self):
        order = make_order('PTG11, Пятигорск, ул. Юлиуса Фучика (357524, Россия)',
                           description='Способ доставки: СДЭК')
        status, ctx = self.creator.classify(order)
        payload = self.creator.build_cdek_order(ctx)
        self.assertEqual(status, 'ready')
        self.assertEqual(payload['tariff_code'], waybills.TARIFF_PVZ)
        self.assertEqual(payload['delivery_point'], 'PTG11')

    def test_no_pvz_mention_goes_to_courier(self):
        order = make_order('121552, Россия, г Москва, ул Ярцевская, д 31, кв 104',
                           description='Способ доставки: СДЭК')
        status, ctx = self.creator.classify(order)
        payload = self.creator.build_cdek_order(ctx)
        self.assertEqual(status, 'ready')
        self.assertEqual(payload['tariff_code'], waybills.TARIFF_COURIER)
        self.assertEqual(payload['to_location']['postal_code'], '121552')

    def test_pickup_point_without_code_is_blocked_not_shipped_by_courier(self):
        """Заказ 08235: «СДЭК ПВЗ» + адрес пункта словами — курьера слать нельзя."""
        order = make_order('Москва, ул. Мневники, 23', comment='СДЭК ПВЗ')
        status, reason = self.creator.classify(order)
        self.assertEqual(status, 'blocked')
        self.assertIn('код', reason)

    def test_own_reason_line_does_not_look_like_pickup_choice(self):
        """Причина, записанная роботом, содержит «ПВЗ» — но это не выбор способа:
        иначе заказ остался бы заблокированным и после правки менеджера."""
        order = make_order(
            '121552, Россия, г Москва, ул Ярцевская, д 31',
            description=('СДЭК КУРЬЕР\n'
                         f'{waybills.REASON_MARKER_PREFIX} указан пункт выдачи, '
                         'но в адресе нет его кода СДЭК — впишите код ПВЗ'))
        status, ctx = self.creator.classify(order)
        self.assertEqual(status, 'ready')
        self.assertEqual(self.creator.build_cdek_order(ctx)['tariff_code'],
                         waybills.TARIFF_COURIER)


class AddressParsingTests(SimpleTestCase):
    """Город (или индекс) отдаём СДЭК отдельным полем — тогда опечатка в улице
    («Мневники» вместо «Мнёвники») перестаёт быть фатальной."""

    def candidates(self, address):
        return waybills.WaybillCreator._to_location_candidates(address)

    def test_postal_code_and_city_come_before_raw_string(self):
        got = self.candidates('121353, Россия, г Москва, ул Беловежская, д 39')
        self.assertEqual(got[0]['postal_code'], '121353')
        self.assertEqual(got[1]['city'], 'Москва')
        self.assertEqual(got[-1], {'address': '121353, Россия, г Москва, ул Беловежская, д 39'})

    def test_city_prefix_is_stripped(self):
        self.assertEqual(self.candidates('г. Ижевск, ул. Пушкинская, 290')[0],
                         {'city': 'Ижевск', 'address': 'ул. Пушкинская, 290'})

    def test_address_without_street_stays_whole(self):
        self.assertEqual(self.candidates('г. Балашиха'), [{'address': 'г. Балашиха'}])

    def test_unrecognized_address_is_blocked_with_cdek_reason(self):
        creator = waybills.WaybillCreator(FakeMs(), FakeCdek())
        creator.state = {'orders': {}}
        order = make_order('Балашиха', description='Способ доставки: СДЭК')
        status, reason = creator.classify(order)
        self.assertEqual(status, 'blocked')
        self.assertIn('не распознал адрес', reason)
