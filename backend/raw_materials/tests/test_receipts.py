from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

import requests
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from api.exceptions import ValidationError
from api.models import UserPageAccess
from api.notifications.raw_materials import receipts_without_series
from raw_materials.models import Batch, BatchMovement, Slot, Supply, SupplyLine
from raw_materials.services.moysklad import supplies as moysklad_supplies
from raw_materials.services.receipts import fill_line, pull_supplies
from raw_materials.tests.factories import batch, material, stock

MS = 'raw_materials.services.moysklad'
BASE = 'https://api.moysklad.ru/api/remap/1.2'


def position(position_id, product, quantity, slot=None, kind='product'):
    row = {'id': position_id, 'quantity': quantity, 'assortment': {'meta': {'href': f'{BASE}/entity/{kind}/{product}', 'type': kind}}}
    if slot:
        row['slot'] = {'meta': {'href': f'{BASE}/entity/store/shuttle/slots/{slot}'}}
    return row


def supply(supply_id, name, positions, applicable=True):
    return {
        'id': supply_id, 'name': name, 'moment': '2026-10-21 15:20:00.000', 'applicable': applicable,
        'agent': {'name': 'ООО «Ревада-Нева»'}, 'positions': {'rows': positions},
    }


class PullSuppliesTests(TestCase):
    def pull(self, rows):
        with patch(f'{MS}.store_id', return_value='shuttle'), patch(f'{MS}.supplies', return_value=rows):
            pull_supplies()

    def test_lines_with_slot_and_only_posted_products(self):
        glucosamine = material('Глюкозамин гидрохлорид')
        Slot.objects.create(external_id='a6', name='A6')
        self.pull([
            supply('s1', '00150', [position('p1', glucosamine.external_id, 400000, slot='a6'), position('p2', 'delivery', 1, kind='service')]),
            supply('s2', '00151', [position('p3', glucosamine.external_id, 1)], applicable=False),
        ])

        line = SupplyLine.objects.get()
        self.assertEqual((line.supply.name, line.quantity, line.slot.name), ('00150', Decimal('400000'), 'A6'))
        self.assertEqual(timezone.localtime(line.supply.moment).hour, 15)

    def test_supply_removed_in_moysklad_keeps_only_lines_with_series(self):
        glucosamine = material()
        self.pull([
            supply('s1', '00150', [position('p1', glucosamine.external_id, 10)]),
            supply('s2', '00151', [position('p2', glucosamine.external_id, 5), position('p3', glucosamine.external_id, 7)]),
        ])
        SupplyLine.objects.filter(external_id='p2').update(batch=batch(glucosamine, '5', series='X'))

        self.pull([])

        self.assertEqual(list(Supply.objects.values_list('name', flat=True)), ['00151'])
        self.assertEqual(list(SupplyLine.objects.values_list('external_id', flat=True)), ['p2'])

    def test_every_page_of_supplies_is_read(self):
        pages = [{'rows': [{'id': str(i)} for i in range(100)]}, {'rows': [{'id': 'last'}]}]
        with patch('raw_materials.services.moysklad.get_json', side_effect=pages) as get:
            rows = moysklad_supplies('shuttle', datetime(2026, 10, 21))
        self.assertEqual(len(rows), 101)
        self.assertEqual(get.call_args_list[1].args[1]['offset'], 100)


class FillLineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vanya')
        self.glucosamine = material('Глюкозамин гидрохлорид')
        stock(self.glucosamine, '400000')
        self.loose = batch(self.glucosamine, '400000')
        self.supply = Supply.objects.create(external_id='s1', name='00150', moment=timezone.make_aware(datetime(2026, 10, 21, 15)), agent='Ревада')
        self.line = SupplyLine.objects.create(supply=self.supply, external_id='p1', material=self.glucosamine, quantity=Decimal('400000'))

    def test_series_takes_the_delivered_quantity_from_the_loose_stock(self):
        fill_line(self.user, self.line.id, ' 2025122709 ', '2028-12-26', 'Shandong')

        created = Batch.objects.get(series='2025122709')
        self.assertEqual((created.quantity, created.expiry_date, created.manufacturer), (Decimal('400000'), date(2028, 12, 26), 'Shandong'))
        self.assertEqual(Batch.objects.get(pk=self.loose.pk).quantity, Decimal('0'))
        self.assertEqual(BatchMovement.objects.filter(kind=BatchMovement.RECEIPT).count(), 2)
        self.line.refresh_from_db()
        self.assertEqual((self.line.batch, self.line.filled_by), (created, self.user))

    def test_without_the_sack_on_stock_nothing_is_recorded(self):
        Batch.objects.filter(pk=self.loose.pk).update(quantity=0)
        with self.assertRaisesMessage(ValidationError, 'Мешок ещё не появился'):
            fill_line(self.user, self.line.id, 'S1', '2028-12-26', '')
        self.line.refresh_from_db()
        self.assertIsNone(self.line.batch)
        self.assertFalse(Batch.objects.filter(series='S1').exists())

    def test_loose_stock_split_over_two_rows_is_gathered(self):
        Batch.objects.filter(pk=self.loose.pk).update(quantity=Decimal('300000'))
        batch(self.glucosamine, '100000', received=(2026, 10, 21))
        fill_line(self.user, self.line.id, 'S1', '2028-12-26', '')
        self.assertEqual(Batch.objects.get(series='S1').quantity, Decimal('400000'))
        self.assertEqual(Batch.objects.filter(series='', quantity__gt=0).count(), 0)

    def test_part_already_issued_from_loose_moves_only_what_is_left(self):
        Batch.objects.filter(pk=self.loose.pk).update(quantity=Decimal('150000'))
        fill_line(self.user, self.line.id, 'S1', '2028-12-26', '')
        self.assertEqual(Batch.objects.get(series='S1').quantity, Decimal('150000'))

    def test_known_series_is_topped_up(self):
        existing = batch(self.glucosamine, '100', series='S1', expiry=(2027, 1, 1))
        fill_line(self.user, self.line.id, 'S1', '2028-12-26', 'Shandong')

        existing.refresh_from_db()
        self.assertEqual((existing.quantity, existing.expiry_date, existing.manufacturer), (Decimal('400100'), date(2028, 12, 26), 'Shandong'))

    def test_fixing_the_series_number_moves_only_the_sack(self):
        existing = batch(self.glucosamine, '100', series='S1', expiry=(2027, 1, 1))
        fill_line(self.user, self.line.id, 'S1', '2027-01-01', '')
        fill_line(self.user, self.line.id, 'S2', '2029-01-01', 'Shandong')

        existing.refresh_from_db()
        fixed = Batch.objects.get(series='S2')
        self.assertEqual((existing.series, existing.quantity), ('S1', Decimal('100')))
        self.assertEqual((fixed.quantity, fixed.expiry_date), (Decimal('400000'), date(2029, 1, 1)))
        self.line.refresh_from_db()
        self.assertEqual(self.line.batch, fixed)

    def test_fixing_expiry_keeps_the_series_and_its_whole_quantity(self):
        fill_line(self.user, self.line.id, 'S1', '2028-12-26', '')
        fill_line(self.user, self.line.id, 'S1', '2029-03-01', 'Shandong')

        only = Batch.objects.get(series='S1')
        self.assertEqual((only.quantity, only.expiry_date, only.manufacturer), (Decimal('400000'), date(2029, 3, 1), 'Shandong'))

    def test_refusals(self):
        tara = material('Ведро', 'шт')
        tara.group = 'Тара'
        tara.save()
        tara_line = SupplyLine.objects.create(supply=self.supply, external_id='p2', material=tara, quantity=Decimal('5'))
        cases = [
            (self.line.id, '', '2028-12-26', 'Впишите серию'),
            (self.line.id, 'S1', '', 'Укажите срок'),
            (self.line.id, 'S1', '26.12.2028', 'Укажите срок'),
            (tara_line.id, 'S1', '2028-12-26', 'Таре серия не нужна'),
            (999, 'S1', '2028-12-26', 'обновите страницу'),
        ]
        for line_id, series, expiry, message in cases:
            with self.subTest(message=message), self.assertRaisesMessage(ValidationError, message):
                fill_line(self.user, line_id, series, expiry, '')

    def test_reminder_until_every_raw_line_has_a_series(self):
        reminders = list(receipts_without_series())
        self.assertEqual(reminders[0].title, 'Приёмка 00150 — впишите серии и сроки')
        self.assertEqual(reminders[0].body, 'Глюкозамин гидрохлорид от Ревада · 21.10')

        fill_line(self.user, self.line.id, 'S1', '2028-12-26', '')
        self.assertEqual(list(receipts_without_series()), [])


class ReceiptsApiTests(TestCase):
    URL = '/api/raw-materials/receipts/'

    def setUp(self):
        self.user = User.objects.create_user('vanya', password='secret')
        UserPageAccess.objects.create(user=self.user, page_key='raw-materials')
        self.client = Client()
        self.client.login(username='vanya', password='secret')
        glucosamine = material('Глюкозамин гидрохлорид')
        old = batch(glucosamine, '0', series='OLD', received=(2026, 9, 1))
        Batch.objects.filter(pk=old.pk).update(manufacturer='Shandong')
        supply_row = Supply.objects.create(external_id='s1', name='00150', moment=timezone.make_aware(datetime(2026, 10, 21, 15)), agent='Ревада')
        self.line = SupplyLine.objects.create(supply=supply_row, external_id='p1', material=glucosamine, quantity=Decimal('400000'))

    def test_list_survives_moysklad_outage_and_suggests_last_manufacturer(self):
        with patch('raw_materials.receipt_views.pull_supplies', side_effect=requests.ConnectionError):
            body = self.client.get(self.URL).json()
        self.assertTrue(body['stale'])
        item = body['items'][0]
        self.assertEqual((item['name'], item['waiting'], item['lines'][0]['manufacturer']), ('00150', 1, 'Shandong'))

    def post_fill(self):
        return self.client.post(f'{self.URL}lines/{self.line.id}/', {'series': 'S1', 'expiry_date': '2028-12-26'}, content_type='application/json')

    def test_sack_already_on_stock_is_recorded_without_asking_moysklad(self):
        batch(self.line.material, '400000')
        with patch('raw_materials.receipt_views.sync_from_moysklad') as sync:
            response = self.post_fill()
        sync.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['waiting'], 0)

    def test_missing_sack_triggers_a_sync_and_its_failure_gives_a_clear_refusal(self):
        with patch('raw_materials.receipt_views.sync_from_moysklad', side_effect=requests.ConnectionError) as sync:
            response = self.post_fill()
        sync.assert_called_once()
        self.assertEqual(response.status_code, 400)
        self.assertIn('Мешок ещё не появился', response.json()['message'])
