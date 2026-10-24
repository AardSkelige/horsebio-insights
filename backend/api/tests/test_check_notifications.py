from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from api import notifications
from api.models import CheckRunResult, HealthCheckException, UserPageAccess
from api.notifications import core
from api.notifications.checks import check_notifications


def _run(script_id, findings=None, exit_code=0):
    run_id = f'r{CheckRunResult.objects.count()}'
    return CheckRunResult.objects.create(script_id=script_id, run_id=run_id, exit_code=exit_code, findings=findings or [])


def _overdue(*names):
    return {
        'key': 'overdue', 'kind': None, 'title': 'Просрочено', 'severity': 'critical',
        'items': [{'ms_id': name, 'object': name, 'detail': 'долг 1 000 ₽', 'severity': 'critical',
                   'ms_href': f'https://online.moysklad.ru/{name}'} for name in names],
    }


class CheckNotificationsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)

    def test_critical_findings_become_a_critical_notification(self):
        _run('horsebio_deadlines', [_overdue('Sweet Horse', 'Candy Horse'), {'key': 'ok', 'title': 'В норме', 'severity': 'ok', 'items': [{'object': 'x'}]}])

        item, = check_notifications()

        self.assertEqual(item.level, core.CRITICAL)
        self.assertEqual(item.title, 'Сроки оплаты: Просрочено — 2')
        self.assertIn('Sweet Horse — долг 1 000 ₽', item.body)
        self.assertEqual(item.route, '/checks/horsebio_deadlines')

    def test_only_the_latest_run_counts(self):
        _run('horsebio_deadlines', [_overdue('Sweet Horse')])
        _run('horsebio_deadlines', [])

        self.assertEqual(list(check_notifications()), [])

    def test_new_finding_changes_the_essence(self):
        _run('horsebio_deadlines', [_overdue('Sweet Horse')])
        before, = check_notifications()
        _run('horsebio_deadlines', [_overdue('Sweet Horse', 'Candy Horse')])
        after, = check_notifications()

        self.assertNotEqual(before.fingerprint, after.fingerprint)

    def test_important_items_are_a_warning(self):
        _run('horsebio_pending_returns', [{'key': 'pending_returns', 'title': 'Ждут поступления', 'severity': None,
                                           'items': [{'object': '№1', 'severity': 'important'}, {'object': '№2'}]}])

        item, = check_notifications()

        self.assertEqual(item.level, core.WARNING)
        self.assertTrue(item.title.endswith('— 1'))

    def test_excepted_health_findings_are_ignored(self):
        HealthCheckException.objects.create(kind='enters', key='e1')
        _run('horsebio_health_check', [{'key': 'enters', 'kind': 'enters', 'title': 'Оприходования', 'items': [{'key': 'e1', 'object': '№1', 'severity': 'important'}]}])

        self.assertEqual(list(check_notifications()), [])

    def test_pending_returns_inside_health_check_are_not_counted(self):
        _run('horsebio_health_check', [{'key': 'pending_returns', 'title': 'Ждут', 'items': [{'object': '№1', 'severity': 'important'}]}])

        self.assertEqual(list(check_notifications()), [])

    def test_failed_run_is_critical(self):
        _run('horsebio_backup', exit_code=1)

        item, = check_notifications()

        self.assertEqual(item.level, core.CRITICAL)
        self.assertEqual(item.title, 'Проверка «Бэкапы» не отработала')

    def test_only_superuser_gets_checks(self):
        _run('horsebio_deadlines', [_overdue('Sweet Horse')])
        boss = User.objects.create_superuser('boss', password='x')
        clerk = User.objects.create_user('clerk', password='x')
        UserPageAccess.objects.create(user=clerk, page_key='deadlines')
        patcher = patch.dict(core._PROVIDERS, {'checks': check_notifications}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.assertEqual([i['source'] for i in notifications.collect(boss)['items'] if i['source'] == 'checks'], ['checks'])
        self.assertFalse([i for i in notifications.collect(clerk)['items'] if i['source'] == 'checks'])
