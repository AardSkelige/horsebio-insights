"""
Tests for /api/checks/ endpoints (дашборд проверок).
"""
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User

from api.models import CheckRunResult
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
