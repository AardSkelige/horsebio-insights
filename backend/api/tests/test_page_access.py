"""Тесты постраничного контроля доступа (api.access + middleware + admin API)."""
import json

from django.test import TestCase, Client
from django.contrib.auth.models import User

from api.models import UserPageAccess
from api.access import ASSIGNABLE_PAGE_KEYS


class PageAccessMiddlewareTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='regular', password='pw')
        self.client.login(username='regular', password='pw')

    def test_denied_without_page_grant(self):
        """Без выданной страницы секционный эндпоинт → 403 от middleware."""
        resp = self.client.post(
            '/api/analysis/cash-flow/',
            data=json.dumps({'date_from': '2026-06-01T00:00:00', 'date_to': '2026-06-30T23:59:59'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(json.loads(resp.content).get('code'), 'FORBIDDEN')

    def test_shared_endpoint_allowed_without_grants(self):
        """Общий эндпоинт (не принадлежит странице) доступен без прав."""
        resp = self.client.get('/api/auth/check/')
        self.assertEqual(resp.status_code, 200)

    def test_allowed_after_grant(self):
        """С выданной страницей middleware пропускает (не 403)."""
        UserPageAccess.objects.create(user=self.user, page_key='cash-flow')
        resp = self.client.post(
            '/api/analysis/cash-flow/',
            data=json.dumps({'date_from': '2026-06-01T00:00:00', 'date_to': '2026-06-30T23:59:59'}),
            content_type='application/json',
        )
        self.assertNotEqual(resp.status_code, 403)

    def test_superuser_class_page_denied_for_regular(self):
        """Суперюзерская страница (/checks) недоступна обычному пользователю."""
        resp = self.client.get('/api/checks/scripts/')
        self.assertEqual(resp.status_code, 403)


class SuperuserBypassTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username='boss', password='pw', email='b@e.ru')
        self.client.login(username='boss', password='pw')

    def test_superuser_sees_checks(self):
        resp = self.client.get('/api/checks/scripts/')
        self.assertNotEqual(resp.status_code, 403)

    def test_check_auth_exposes_allowed_pages(self):
        resp = self.client.get('/api/auth/check/')
        data = json.loads(resp.content)
        self.assertTrue(data['isSuperuser'])
        # суперюзеру доступны все назначаемые страницы (плюс суперюзерские)
        for key in ASSIGNABLE_PAGE_KEYS:
            self.assertIn(key, data['allowedPages'])


class PagesAccessAdminApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_superuser(username='boss', password='pw', email='b@e.ru')
        self.target = User.objects.create_user(username='bob', password='pw')

    def test_regular_user_forbidden(self):
        self.client.login(username='bob', password='pw')
        resp = self.client.get('/api/auth/pages-access/')
        self.assertEqual(resp.status_code, 403)

    def test_superuser_lists_and_saves(self):
        self.client.login(username='boss', password='pw')

        resp = self.client.get('/api/auth/pages-access/')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)['data']
        self.assertTrue(any(u['username'] == 'bob' for u in data['users']))
        self.assertTrue(all(not p['key'] in ('checks', 'system-analytics') for p in data['pages']))

        # сохраняем доступ + отсекаем мусор и суперюзерские ключи
        resp = self.client.post(
            '/api/auth/pages-access/',
            data=json.dumps({'user_id': self.target.id, 'pages': ['abc', 'cash-flow', 'checks', 'nonexistent']}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        saved = json.loads(resp.content)['data']['pages']
        self.assertEqual(saved, ['abc', 'cash-flow'])
        self.assertEqual(
            set(UserPageAccess.objects.filter(user=self.target).values_list('page_key', flat=True)),
            {'abc', 'cash-flow'},
        )

    def test_cannot_edit_superuser(self):
        self.client.login(username='boss', password='pw')
        resp = self.client.post(
            '/api/auth/pages-access/',
            data=json.dumps({'user_id': self.admin.id, 'pages': ['abc']}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
