"""
Tests for /api/checks/ endpoints (дашборд проверок).
"""
from datetime import timedelta

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from api.models import CheckRunResult, HealthCheckException
from api.services.health_checks import (
    EXPIRE_DAYS, cleanup_expired_exceptions, cleanup_resolved_deviations,
)
from api.views.scripts_monitor import HEALTH_CHECK_SCRIPT_ID


class ChecksRunDeleteTests(TestCase):
    """DELETE /api/checks/scripts/{id}/runs/{run_id}/"""

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser('admin', 'admin@test.ru', 'pass')
        self.client.force_login(self.admin)
        self.run = CheckRunResult.objects.create(
            script_id=HEALTH_CHECK_SCRIPT_ID,
            run_id='20260626_073800',
            exit_code=0,
            duration_sec=10.0,
            summary={'critical': 1, 'important': 0, 'warnings': 2},
        )

    def _url(self, run_id, script_id=HEALTH_CHECK_SCRIPT_ID):
        return reverse('api:checks_run_delete', args=[script_id, run_id])

    def test_delete_removes_run(self):
        resp = self.client.delete(self._url(self.run.run_id))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['status'], 'ok')
        self.assertFalse(CheckRunResult.objects.filter(pk=self.run.pk).exists())

    def test_delete_unknown_run_returns_404(self):
        resp = self.client.delete(self._url('19990101_000000'))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(CheckRunResult.objects.filter(pk=self.run.pk).exists())

    def test_delete_unknown_script_returns_404(self):
        resp = self.client.delete(self._url(self.run.run_id, script_id='no_such_script'))
        self.assertEqual(resp.status_code, 404)

    def test_requires_superuser(self):
        user = User.objects.create_user('user', 'user@test.ru', 'pass')
        self.client.force_login(user)
        resp = self.client.delete(self._url(self.run.run_id))
        self.assertEqual(resp.status_code, 401)
        self.assertTrue(CheckRunResult.objects.filter(pk=self.run.pk).exists())

    def test_get_method_not_allowed(self):
        resp = self.client.get(self._url(self.run.run_id))
        self.assertEqual(resp.status_code, 405)


class CleanupExpiredExceptionsTests(TestCase):
    """Автоочистка документных исключений, вышедших из окна сканирования."""

    def setUp(self):
        # Сид-миграция 0007 наполняет таблицу из data/*.json — тестам нужна чистая
        HealthCheckException.objects.all().delete()

    def _age(self, exc, days):
        HealthCheckException.objects.filter(pk=exc.pk).update(
            created_at=timezone.now() - timedelta(days=days))

    def test_deletes_only_expired_doc_kinds(self):
        fresh = HealthCheckException.objects.create(kind='enters', key='fresh')
        old_doc = HealthCheckException.objects.create(kind='inventories', key='old')
        jump = HealthCheckException.objects.create(kind='supply_jumps', key='товар')
        deviation = HealthCheckException.objects.create(kind='deviations', key='1-001')
        self._age(old_doc, EXPIRE_DAYS + 30)
        self._age(jump, EXPIRE_DAYS + 30)
        self._age(deviation, EXPIRE_DAYS + 30)

        self.assertEqual(cleanup_expired_exceptions(), 1)

        left = set(HealthCheckException.objects.values_list('pk', flat=True))
        self.assertEqual(left, {fresh.pk, jump.pk, deviation.pk})

    def test_noop_when_nothing_expired(self):
        HealthCheckException.objects.create(kind='enters', key='fresh')
        self.assertEqual(cleanup_expired_exceptions(), 0)
        self.assertEqual(HealthCheckException.objects.count(), 1)


class CleanupResolvedDeviationsTests(TestCase):
    """Автоудаление deviations «исправлено»/«ошибка-некритично», ушедших из отчёта."""

    def setUp(self):
        HealthCheckException.objects.all().delete()
        self.fixed_gone = HealthCheckException.objects.create(
            kind='deviations', key='1-150', extra={'status': 'исправлено'})
        self.fixed_still = HealthCheckException.objects.create(
            kind='deviations', key='1-151', extra={'status': 'исправлено'})
        self.minor_gone = HealthCheckException.objects.create(
            kind='deviations', key='3-045', extra={'status': 'ошибка-некритично'})
        self.norm_gone = HealthCheckException.objects.create(
            kind='deviations', key='1-215', extra={'status': 'норма'})

    def _categories(self):
        # В отчёте всё ещё фигурирует только 1-151
        return [
            {'kind': 'deviations', 'key': 'important',
             'items': [{'key': '1-151', 'object': 'Товар'}]},
            {'kind': None, 'key': 'stale_drafts',
             'items': [{'key': '1-150', 'object': 'не deviations — не считается'}]},
        ]

    def test_deletes_resolved_absent_from_report(self):
        self.assertEqual(cleanup_resolved_deviations(self._categories()), 2)
        left = set(HealthCheckException.objects.values_list('key', flat=True))
        # Ушли закрытые 1-150 и 3-045; осталась видимая 1-151 и «норма» 1-215
        self.assertEqual(left, {'1-151', '1-215'})

    def test_norma_never_deleted(self):
        cleanup_resolved_deviations([])
        self.assertTrue(HealthCheckException.objects.filter(key='1-215').exists())
