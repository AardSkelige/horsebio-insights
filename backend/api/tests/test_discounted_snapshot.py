"""
Раздел «Уценка» читает снимок из базы, а не МойСклад.

Смысл переезда: одиннадцать обращений к чужому API стояли в запросе
пользователя, и при отказе по лимиту (429) страница показывала не старые
данные, а ничего. Уведомления дёргали ту же сборку на каждый опрос
колокольчика — то есть у всех раз в пять минут.
"""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase

from api.models import SectionSnapshot, UserPageAccess

SNAPSHOT = {
    'positions': [{'id': 'p-1', 'article': 'A-UC', 'quantity': 3, 'state': 'ok'}],
    'summary': {'positions': 1, 'units': 3, 'sum': 900.0, 'sum_cost': 500.0, 'needs_action': 0},
    'analytics': {},
    'rules': {'discount_rate': 0.3, 'months_to_delist': 2},
    'generated_at': '2026-09-10T09:00:00',
}


class PageReadsTheSnapshotTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        user = User.objects.create_user('lera', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client = Client()
        self.client.login(username='lera', password='secret')

    def test_open_page_does_not_touch_moysklad(self):
        SectionSnapshot.store('discounted', SNAPSHOT)

        with patch('api.services.discounted_report._build_data') as build:
            payload = self.client.get('/api/discounted/').json()

        build.assert_not_called()
        self.assertEqual(payload['positions'][0]['article'], 'A-UC')
        self.assertEqual(payload['generated_at'], '2026-09-10T09:00:00')

    def test_first_open_before_any_run_builds_once_and_stores(self):
        """Пустая страница до ближайшего прогона хуже трёх секунд ожидания."""
        with patch('api.services.discounted_report._build_data', return_value=SNAPSHOT) as build:
            payload = self.client.get('/api/discounted/').json()

        build.assert_called_once()
        self.assertEqual(payload['summary']['positions'], 1)
        self.assertEqual(SectionSnapshot.stored('discounted').payload['generated_at'],
                         '2026-09-10T09:00:00')

    def test_refresh_rebuilds_and_replaces_the_snapshot(self):
        SectionSnapshot.store('discounted', {'positions': [], 'summary': {}, 'generated_at': 'старое'})

        with patch('api.services.discounted_report._build_data', return_value=SNAPSHOT) as build:
            payload = self.client.get('/api/discounted/?refresh=1').json()

        build.assert_called_once()
        self.assertEqual(payload['generated_at'], '2026-09-10T09:00:00')
        self.assertEqual(SectionSnapshot.objects.count(), 1, 'снимок один, а не история')


class NotificationsReadTheSnapshotTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_bell_takes_positions_from_the_database(self):
        """Колокольчик опрашивают из любого раздела и у каждого раз в пять минут."""
        from api.services.discounted_report import positions_snapshot

        SectionSnapshot.store('discounted', SNAPSHOT)

        with patch('api.services.discounted_report._build_positions') as build:
            positions = positions_snapshot()

        build.assert_not_called()
        self.assertEqual(positions, SNAPSHOT['positions'])

    def test_without_a_snapshot_falls_back_to_a_light_build(self):
        """До первой сборки считаем облегчённо — но один раз, дальше из кеша."""
        from api.services.discounted_report import positions_snapshot

        with patch('api.services.discounted_report._build_positions', return_value=[]) as build:
            positions_snapshot()
            positions_snapshot()

        build.assert_called_once()


class ActionsInvalidateTheSnapshotTests(TestCase):
    """Снятие с продажи и публикация меняют то, что нарисовано в снимке."""

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_invalidation_forgets_the_snapshot(self):
        """Иначе колокольчик до получаса зовёт сделать уже сделанное: снимок
        пересобирает расписание, а действие человека его не трогало."""
        from api.services.discounted_report import invalidate_cache

        SectionSnapshot.store('discounted', SNAPSHOT)

        invalidate_cache()

        self.assertIsNone(SectionSnapshot.stored('discounted'))


class BuildIsGuardedTests(TestCase):
    """Сборка одна на раздел, и после падения раздел отдыхает.

    Без этого сломанный МойСклад означал бы шквал сборок: у каждого, кто открыл
    страницу, и на каждый F5 — по одиннадцать запросов, то есть усиление ровно
    той беды, ради которой снимки заводились.
    """

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        user = User.objects.create_user('lera', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client = Client()
        self.client.login(username='lera', password='secret')

    def test_failed_build_does_not_retry_on_every_request(self):
        """Первая попытка сходила и упала, вторая даже не пошла — замок
        дотлевает свой срок и работает паузой."""
        with patch('api.services.discounted_report._build_data', side_effect=RuntimeError('429')) as build:
            first = self.client.get('/api/discounted/')
            second = self.client.get('/api/discounted/')

        build.assert_called_once()
        self.assertGreaterEqual(first.status_code, 500)
        self.assertGreaterEqual(second.status_code, 400)

    def test_while_a_build_is_running_the_old_snapshot_is_served(self):
        from api.services import section_snapshots

        SectionSnapshot.store('discounted', SNAPSHOT)
        cache.add(f'section_snapshot_build:discounted', True, 60)

        payload = section_snapshots.rebuild('discounted', lambda: self.fail('вторая сборка'))

        self.assertEqual(payload['generated_at'], '2026-09-10T09:00:00')


class CommandTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_command_stores_the_snapshot(self):
        with patch('api.services.discounted_report._build_data', return_value=SNAPSHOT):
            call_command('build_discounted_snapshot')

        self.assertEqual(SectionSnapshot.stored('discounted').payload['summary']['units'], 3)

    def test_second_run_replaces_the_first(self):
        with patch('api.services.discounted_report._build_data', return_value=SNAPSHOT):
            call_command('build_discounted_snapshot')
        with patch('api.services.discounted_report._build_data',
                   return_value=dict(SNAPSHOT, generated_at='2026-09-10T09:30:00')):
            call_command('build_discounted_snapshot')

        self.assertEqual(SectionSnapshot.objects.count(), 1)
        self.assertEqual(SectionSnapshot.stored('discounted').payload['generated_at'],
                         '2026-09-10T09:30:00')
