"""
Переезд состояния робота накладных СДЭК из файла в базу.

Состояние на томе держалось на том, что том не забыли смонтировать: забыли бы —
робот начал бы с чистого листа и завёл вторую накладную на уехавший заказ.
"""
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import CdekWaybillState

STATE = {
    'orders': {
        'order-1': {'name': '06317', 'status': 'created', 'cdek_number': '10299533136'},
        'order-2': {'name': '06318', 'status': 'blocked', 'reason': 'нет телефона'},
    }
}


def _state_file(data=None):
    tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
    json.dump(STATE if data is None else data, tmp, ensure_ascii=False)
    tmp.close()
    return Path(tmp.name)


class ImportCdekWaybillsTests(TestCase):
    def test_import_moves_every_order(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_cdek_waybills', '--path', str(path))

        self.assertEqual(CdekWaybillState.objects.count(), 2)
        row = CdekWaybillState.objects.get(order_id='order-1')
        self.assertEqual(row.payload['cdek_number'], '10299533136')

    def test_import_is_idempotent(self):
        """Переносить можно до выката робота, проверять и переносить снова."""
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_cdek_waybills', '--path', str(path))
        call_command('import_cdek_waybills', '--path', str(path))

        self.assertEqual(CdekWaybillState.objects.count(), 2)

    def test_import_updates_changed_record(self):
        path = _state_file()
        self.addCleanup(path.unlink)
        CdekWaybillState.objects.create(order_id='order-1', payload={'status': 'blocked'})

        call_command('import_cdek_waybills', '--path', str(path))

        self.assertEqual(CdekWaybillState.objects.get(order_id='order-1').payload['status'],
                         'created')

    def test_dry_run_writes_nothing(self):
        path = _state_file()
        self.addCleanup(path.unlink)

        call_command('import_cdek_waybills', '--path', str(path), '--dry-run')

        self.assertEqual(CdekWaybillState.objects.count(), 0)

    def test_missing_file_is_an_error_and_not_an_empty_import(self):
        """Молчаливый успех на отсутствующем файле означал бы, что состояние
        «перенесли», а робот начал с чистого листа."""
        with self.assertRaises(CommandError):
            call_command('import_cdek_waybills', '--path', '/nope/state.json')

    def test_record_keeps_unknown_keys(self):
        """Робот дописывает поля по ходу дела; жёсткая схема их бы потеряла."""
        path = _state_file({'orders': {'order-3': {'что-то_новое': [1, 2, 3]}}})
        self.addCleanup(path.unlink)

        call_command('import_cdek_waybills', '--path', str(path))

        self.assertEqual(CdekWaybillState.objects.get(order_id='order-3').payload,
                         {'что-то_новое': [1, 2, 3]})
