import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.test import Client, TestCase

from api.exceptions import ExternalServiceError, ValidationError
from api.models import UserPageAccess
from raw_materials.models import Batch, BatchMovement, Issue, MaterialStock, Slot, SlotStock
from raw_materials.services import moysklad
from raw_materials.services.issue import describe, issue
from raw_materials.tests.factories import batch, material, stock

CREATE_MOVE = 'raw_materials.services.moysklad.create_move'
MOVE = {'id': 'move-1', 'name': '00285'}


class IssueTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('vanya', first_name='Иван', last_name='Петров')
        self.slot = Slot.objects.create(external_id='slot-a6', name='A6')
        self.chondroitin = material()
        stock(self.chondroitin, '150', slot=self.slot)
        SlotStock.objects.create(material=self.chondroitin, slot=self.slot, quantity=Decimal('150'))
        self.fresh = batch(self.chondroitin, '100', series='GN1', expiry=(2027, 1, 1))
        self.loose = batch(self.chondroitin, '50')

    def run_issue(self, lines, key=None):
        with patch(CREATE_MOVE, return_value=MOVE) as create:
            record = issue(self.user, key or uuid.uuid4(), lines, 'Рома')
        return record, create

    def test_writes_one_move_and_takes_quantity_from_the_chosen_series(self):
        record, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 30}, {'batch': self.loose.id, 'quantity': '5'}])

        code, description, positions = create.call_args.args
        self.assertEqual(code, str(record.key))
        self.assertEqual(description, 'Иван Петров, выдача сырья. Получил: Рома')
        self.assertEqual(positions, [(self.chondroitin.external_id, 'slot-a6', Decimal('35'))])

        self.fresh.refresh_from_db()
        self.loose.refresh_from_db()
        self.assertEqual((self.fresh.quantity, self.loose.quantity), (Decimal('70'), Decimal('45')))
        self.assertEqual(MaterialStock.objects.get().quantity, Decimal('115'))
        self.assertEqual(BatchMovement.objects.filter(kind=BatchMovement.ISSUE).count(), 2)
        self.assertEqual((record.moysklad_name, record.lines.count()), ('00285', 2))

    def test_same_key_twice_does_not_issue_twice(self):
        key = uuid.uuid4()
        self.run_issue([{'batch': self.fresh.id, 'quantity': 10}], key)
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 10}], key)

        create.assert_not_called()
        self.assertEqual(Batch.objects.get(pk=self.fresh.pk).quantity, Decimal('90'))
        self.assertEqual(Issue.objects.count(), 1)

    def test_more_than_the_series_holds_is_refused_before_moysklad(self):
        with self.assertRaises(ValidationError):
            self.run_issue([{'batch': self.fresh.id, 'quantity': 60}, {'batch': self.fresh.id, 'quantity': 60}])
        self.assertFalse(Issue.objects.exists())

    def test_without_receiver_is_refused(self):
        for receiver in ('', '   ', None):
            with self.subTest(receiver=receiver), self.assertRaisesMessage(ValidationError, 'Укажите, кто получил'):
                with patch(CREATE_MOVE, return_value=MOVE):
                    issue(self.user, uuid.uuid4(), [{'batch': self.fresh.id, 'quantity': 1}], receiver)

    def test_zero_or_garbage_is_refused(self):
        for lines in ([], [{'batch': self.fresh.id, 'quantity': 0}], [{'batch': 'x', 'quantity': 1}]):
            with self.subTest(lines=lines), self.assertRaises(ValidationError):
                self.run_issue(lines)

    def test_moysklad_refusal_leaves_nothing_behind(self):
        response = MagicMock()
        response.json.return_value = {'errors': [{'error': 'Нельзя переместить больше, чем есть в ячейке'}]}
        with patch(CREATE_MOVE, side_effect=requests.HTTPError(response=response)):
            with self.assertRaisesMessage(ExternalServiceError, 'Нельзя переместить больше'):
                issue(self.user, uuid.uuid4(), [{'batch': self.fresh.id, 'quantity': 10}], 'Рома')

        self.assertFalse(Issue.objects.exists())
        self.assertEqual(Batch.objects.get(pk=self.fresh.pk).quantity, Decimal('100'))


    def spread(self):
        c2 = Slot.objects.create(external_id='slot-c2', name='C2')
        SlotStock.objects.filter(slot=self.slot).update(quantity=Decimal('70'))
        SlotStock.objects.create(material=self.chondroitin, slot=c2, quantity=Decimal('80'))

    def test_takes_from_the_scanned_slot_first_and_the_rest_from_others(self):
        self.spread()
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 100, 'slot': 'C2'}])
        self.assertEqual(create.call_args.args[2], [
            (self.chondroitin.external_id, 'slot-c2', Decimal('80')),
            (self.chondroitin.external_id, 'slot-a6', Decimal('20')),
        ])
        self.assertEqual(Issue.objects.get().lines.get().slot.name, 'C2')

    def test_without_a_scanned_slot_starts_from_home(self):
        self.spread()
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 100}])
        self.assertEqual([slot for _, slot, _ in create.call_args.args[2]], ['slot-a6', 'slot-c2'])

    def test_more_than_the_slots_hold_goes_without_a_slot(self):
        SlotStock.objects.update(quantity=Decimal('10'))
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 30}])
        self.assertEqual([(slot, q) for _, slot, q in create.call_args.args[2]], [('slot-a6', Decimal('10')), (None, Decimal('20'))])

    def test_slot_stock_shrinks_right_away_so_the_next_issue_goes_elsewhere(self):
        self.spread()
        self.run_issue([{'batch': self.fresh.id, 'quantity': 60, 'slot': 'A6'}])
        self.assertEqual(SlotStock.objects.get(slot=self.slot).quantity, Decimal('10'))

        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 30, 'slot': 'A6'}])
        self.assertEqual([(slot, q) for _, slot, q in create.call_args.args[2]], [('slot-a6', Decimal('10')), ('slot-c2', Decimal('20'))])
        self.assertFalse(SlotStock.objects.filter(slot=self.slot).exists())

    def test_before_the_first_sync_takes_everything_from_home(self):
        SlotStock.objects.all().delete()
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': 30}])
        self.assertEqual(create.call_args.args[2], [(self.chondroitin.external_id, 'slot-a6', Decimal('30'))])

    def test_move_is_deleted_when_our_record_fails(self):
        with patch(CREATE_MOVE, return_value=MOVE), \
                patch('raw_materials.services.issue._record', side_effect=RuntimeError), \
                patch('raw_materials.services.moysklad.discard_move') as discard:
            with self.assertRaises(RuntimeError):
                issue(self.user, uuid.uuid4(), [{'batch': self.fresh.id, 'quantity': 10}], 'Рома')
        discard.assert_called_once_with('move-1')
        self.assertFalse(Issue.objects.exists())

    def test_quantity_is_rounded_to_a_milligram_and_nan_is_refused(self):
        _, create = self.run_issue([{'batch': self.fresh.id, 'quantity': '0.30000000000000004'}])
        self.assertEqual(create.call_args.args[2][0][2], Decimal('0.300'))
        for bad in ('NaN', 'Infinity', '0.0004'):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.run_issue([{'batch': self.fresh.id, 'quantity': bad}])

    def test_series_without_stock_row_is_a_clear_refusal(self):
        orphan = batch(material('Без остатка'), '5', series='X')
        with self.assertRaisesMessage(ValidationError, 'нет остатка в МойСклад'):
            self.run_issue([{'batch': orphan.id, 'quantity': 1}])


class DescribeTests(TestCase):
    def test_names_who_and_what_was_issued(self):
        vanya = User(first_name='Иван', last_name='Петров')
        raw, tara = material(), material('Ведро 2 литра', 'шт')
        tara.group = 'Тара'
        self.assertEqual(describe(vanya, {raw}, 'Рома'), 'Иван Петров, выдача сырья. Получил: Рома')
        self.assertEqual(describe(vanya, {tara}, 'Рома'), 'Иван Петров, выдача тары. Получил: Рома')
        self.assertEqual(describe(vanya, {raw, tara}, 'Рома'), 'Иван Петров, выдача сырья и тары. Получил: Рома')
        self.assertEqual(describe(User(username='vapan1'), {raw}, 'Рома'), 'vapan1, выдача сырья. Получил: Рома')


class CreateMoveTests(TestCase):
    def test_repeat_left_by_a_retried_request_is_deleted(self):
        with patch.object(moysklad, 'store_id', return_value='shuttle'), \
                patch.object(moysklad, '_id_by_name', return_value='target'), \
                patch.object(moysklad, 'post_json', return_value=MOVE) as post, \
                patch.object(moysklad, 'get_json', return_value={'rows': [{'id': 'move-1'}, {'id': 'move-2'}]}), \
                patch.object(moysklad, 'delete') as delete:
            moysklad.create_move('key-1', 'Ваня, выдача сырья', [('product', 'slot', Decimal('1.5'))])

        body = post.call_args.args[1]
        self.assertEqual((body['externalCode'], body['applicable']), ('key-1', True))
        self.assertEqual(body['positions'][0]['quantity'], 1.5)
        self.assertTrue(body['positions'][0]['sourceSlot']['meta']['href'].endswith('/store/shuttle/slots/slot'))
        delete.assert_called_once_with('/entity/move/move-2')


class IssuesApiTests(TestCase):
    URL = '/api/raw-materials/issues/'

    def setUp(self):
        self.user = User.objects.create_user('vanya', password='secret', first_name='Ваня')
        self.client = Client()
        self.client.login(username='vanya', password='secret')
        chondroitin = material()
        stock(chondroitin, '100', slot=Slot.objects.create(external_id='s', name='A6'))
        self.batch = batch(chondroitin, '100', series='GN1')

    def test_closed_without_page_access(self):
        self.assertEqual(self.client.get(self.URL).status_code, 403)

    def test_issue_then_see_it_in_the_journal(self):
        UserPageAccess.objects.create(user=self.user, page_key='raw-materials')
        body = {'key': str(uuid.uuid4()), 'receiver': 'Рома', 'lines': [{'batch': self.batch.id, 'quantity': 25}]}
        with patch(CREATE_MOVE, return_value=MOVE):
            created = self.client.post(self.URL, body, content_type='application/json')

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()['moysklad_url'], 'https://online.moysklad.ru/app/#move/edit?id=move-1')
        line = self.client.get(self.URL).json()['items'][0]['lines'][0]
        self.assertEqual((line['series'], line['slot'], line['quantity']), ('GN1', 'A6', 25.0))

    def test_broken_bodies_are_refused(self):
        UserPageAccess.objects.create(user=self.user, page_key='raw-materials')
        for body in ({'lines': []}, [], {'key': str(uuid.uuid4()), 'lines': 'x'}, {'key': str(uuid.uuid4()), 'lines': [1]}):
            with self.subTest(body=body):
                response = self.client.post(self.URL, body, content_type='application/json')
                self.assertEqual(response.status_code, 400)


class CreateMoveFailureTests(TestCase):
    def test_timed_out_post_cleans_up_whatever_reached_moysklad(self):
        with patch.object(moysklad, 'store_id', return_value='shuttle'), \
                patch.object(moysklad, '_id_by_name', return_value='target'), \
                patch.object(moysklad, 'post_json', side_effect=requests.Timeout), \
                patch.object(moysklad, 'get_json', return_value={'rows': [{'id': 'late'}]}), \
                patch.object(moysklad, 'delete') as delete:
            with self.assertRaises(requests.Timeout):
                moysklad.create_move('key-1', 'Иван Петров, выдача сырья', [('product', None, Decimal('1'))])
        delete.assert_called_once_with('/entity/move/late')
