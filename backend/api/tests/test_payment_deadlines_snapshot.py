"""
Снимок сроков оплаты в базе.

Снимок — не состояние робота, а его результат: он пересобирает его каждый
прогон. Но читает снимок страница, и файл на томе означал бы пустую страницу
от каждого деплоя до ближайшего ночного прогона.
"""
from django.contrib.auth.models import User
from django.test import TestCase

from api.models import PaymentDeadlineSnapshot

SNAPSHOT = {
    'generated_at': '2026-09-07 09:20',
    'overdue': [{'doc_name': '04646', 'days_left': -67, 'is_paid': False}],
    'summary': {'overdue': 1, 'warning': 0, 'ok': 3, 'paid': 12},
}


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
