"""
Разделы FBO читают снимок из базы, а не МойСклад.

Те же соображения, что у уценки: чужой API стоял в запросе пользователя,
и при отказе по лимиту раздел показывал не старые данные, а ничего.
Здесь запросов меньше (3 и 4 против 11), но зависимость та же.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase

from api.models import SectionSnapshot, UserPageAccess

STOCK_SNAPSHOT = {
    'generated_at': '2026-09-10T09:00:00+03:00',
    'store': 'Склад готовой продукции',
    'items': [
        {'article': 'A', 'name': 'Гель', 'quantity': 4, 'in_transit': 0,
         'below_minimum': False, 'is_empty': False},
    ],
}

FBO_SNAPSHOT = {
    'statistics': {'fbo_orders': 2,
                   'overdue_orders': 9, 'overdue_sum': 2472240.0, 'overdue_oldest_days': 595,
                   'start_date': '2026-08-11T00:00:00', 'end_date': '2026-09-10T00:00:00',
                   'last_update': '2026-09-10T09:00:00'},
    'products': [{'name': 'Гель', 'quantity': 3}],
    'orders': [{'id': 'o-1', 'name': '00123'}],
}


class _SectionTestCase(TestCase):
    page_key = ''
    url = ''

    def setUp(self):
        user = User.objects.create_user('lera', password='secret')
        UserPageAccess.objects.create(user=user, page_key=self.page_key)
        self.client = Client()
        self.client.login(username='lera', password='secret')


class FboStockPageTests(_SectionTestCase):
    page_key = 'fbo-stock'
    url = '/api/analysis/fbo-stock/'

    def test_open_page_does_not_touch_moysklad(self):
        SectionSnapshot.store('fbo-stock', STOCK_SNAPSHOT)

        with patch('api.views.fbo_stock._build_data') as build:
            payload = self.client.get(self.url).json()

        build.assert_not_called()
        self.assertEqual(payload['data']['items'][0]['article'], 'A')

    def test_first_open_before_any_run_builds_once(self):
        with patch('api.views.fbo_stock._build_data', return_value=STOCK_SNAPSHOT) as build:
            self.client.get(self.url)

        build.assert_called_once()
        self.assertIsNotNone(SectionSnapshot.stored('fbo-stock'))

    def test_refresh_rebuilds(self):
        SectionSnapshot.store('fbo-stock', dict(STOCK_SNAPSHOT, store='старое'))

        with patch('api.views.fbo_stock._build_data', return_value=STOCK_SNAPSHOT) as build:
            payload = self.client.get(f'{self.url}?refresh=1').json()

        build.assert_called_once()
        self.assertEqual(payload['data']['store'], 'Склад готовой продукции')

    def test_command_stores_the_snapshot(self):
        with patch('api.views.fbo_stock._build_data', return_value=STOCK_SNAPSHOT):
            call_command('build_fbo_stock_snapshot')

        self.assertEqual(SectionSnapshot.stored('fbo-stock').payload['store'],
                         'Склад готовой продукции')


class FboOrdersPageTests(_SectionTestCase):
    page_key = 'fbo'
    url = '/api/analysis/fbo/'

    def test_open_page_does_not_touch_moysklad(self):
        SectionSnapshot.store('fbo', FBO_SNAPSHOT)

        with patch('api.views.fbo._build_fbo_analysis_data') as build:
            payload = self.client.get(self.url).json()

        build.assert_not_called()
        self.assertEqual(payload['statistics']['fbo_orders'], 2)

    def test_first_open_before_any_run_builds_once(self):
        with patch('api.views.fbo._build_fbo_analysis_data', return_value=FBO_SNAPSHOT) as build:
            self.client.get(self.url)

        build.assert_called_once()
        self.assertIsNotNone(SectionSnapshot.stored('fbo'))

    def test_refresh_rebuilds(self):
        SectionSnapshot.store('fbo', dict(FBO_SNAPSHOT, products=[]))

        with patch('api.views.fbo._build_fbo_analysis_data', return_value=FBO_SNAPSHOT) as build:
            payload = self.client.get(f'{self.url}?refresh=1').json()

        build.assert_called_once()
        self.assertEqual(len(payload['products']), 1)

    def test_command_stores_the_snapshot(self):
        with patch('api.views.fbo._build_fbo_analysis_data', return_value=FBO_SNAPSHOT):
            call_command('build_fbo_snapshot')

        self.assertEqual(SectionSnapshot.stored('fbo').payload['statistics']['overdue_orders'], 9)


class SnapshotsShareOneTableTests(TestCase):
    """Строка на раздел: одна таблица вместо трёх почти одинаковых."""

    def test_sections_do_not_overwrite_each_other(self):
        SectionSnapshot.store('fbo', FBO_SNAPSHOT)
        SectionSnapshot.store('fbo-stock', STOCK_SNAPSHOT)
        SectionSnapshot.store('fbo', dict(FBO_SNAPSHOT, products=[]))

        self.assertEqual(SectionSnapshot.objects.count(), 2)
        self.assertEqual(SectionSnapshot.stored('fbo-stock').payload['store'],
                         'Склад готовой продукции')
        self.assertEqual(SectionSnapshot.stored('fbo').payload['products'], [])
