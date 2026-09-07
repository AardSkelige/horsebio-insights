"""
Переезд снимка сроков оплаты из файла в базу.

Снимок — не состояние робота, а его результат: он пересобирает его каждый
прогон. Но читает снимок страница, и файл на томе означал бы пустую страницу
от каждого деплоя до ближайшего ночного прогона.
"""
import json
import tempfile
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from api.models import PaymentDeadlineSnapshot

SNAPSHOT = {
    'generated_at': '2026-09-07 09:20',
    'overdue': [{'doc_name': '04646', 'days_left': -67, 'is_paid': False}],
    'summary': {'overdue': 1, 'warning': 0, 'ok': 3, 'paid': 12},
}


class ImportPaymentDeadlinesTests(TestCase):
    def _file(self, data=None):
        tmp = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(SNAPSHOT if data is None else data, tmp, ensure_ascii=False)
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(path.unlink)
        return path

    def test_import_stores_the_snapshot(self):
        call_command('import_payment_deadlines', '--path', str(self._file()))

        self.assertEqual(PaymentDeadlineSnapshot.get().payload['summary']['overdue'], 1)

    def test_import_replaces_the_previous_snapshot(self):
        """Строка одна: прошлые снимки никому не нужны, робот ходит ежедневно."""
        call_command('import_payment_deadlines', '--path', str(self._file()))
        call_command('import_payment_deadlines', '--path', str(self._file()))

        self.assertEqual(PaymentDeadlineSnapshot.objects.count(), 1)

    def test_foreign_file_is_refused(self):
        with self.assertRaisesRegex(CommandError, 'не похоже на снимок'):
            call_command('import_payment_deadlines', '--path', str(self._file({'что': 'то'})))


class DeadlinesViewTests(TestCase):
    def setUp(self):
        from api.access import grant_all_assignable_pages

        user = User.objects.create_user('user', password='password')
        grant_all_assignable_pages(user)
        self.client.force_login(user)

    def test_page_says_nothing_yet_when_there_is_no_snapshot(self):
        payload = self.client.get('/api/deadlines/').json()

        self.assertFalse(payload['available'])

    def test_page_reads_the_snapshot_from_the_database(self):
        PaymentDeadlineSnapshot.store(SNAPSHOT)

        payload = self.client.get('/api/deadlines/').json()

        self.assertTrue(payload['available'])
        self.assertEqual(payload['summary']['overdue'], 1)
        self.assertFalse(payload['stale'], 'снимок только что записан')
