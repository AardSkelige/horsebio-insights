import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.models import UserHomePreference, UserPageEvent


class HomePreferencesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'lilia', password='password', first_name='Лиля'
        )
        self.client.force_login(self.user)

    def test_preferences_are_private_and_recent_pages_are_unique(self):
        UserPageEvent.objects.create(
            user=self.user, page_path='/inventory', page_name='Мониторинг', duration_seconds=10
        )
        UserPageEvent.objects.create(
            user=self.user, page_path='/analysis/abc', page_name='ABC Анализ', duration_seconds=10
        )
        UserPageEvent.objects.create(
            user=self.user, page_path='/inventory', page_name='Мониторинг', duration_seconds=10
        )

        response = self.client.get('/api/auth/home/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['pinnedPaths'], [])
        self.assertEqual(
            response.json()['data']['recentPaths'],
            ['/inventory', '/analysis/abc'],
        )
        self.assertTrue(UserHomePreference.objects.filter(user=self.user).exists())

    def test_pinned_paths_are_saved_for_account(self):
        response = self.client.patch(
            '/api/auth/home/',
            data=json.dumps({'pinnedPaths': ['/inventory', '/analysis/abc']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            UserHomePreference.objects.get(user=self.user).pinned_paths,
            ['/inventory', '/analysis/abc'],
        )

    def test_rejects_invalid_or_too_many_paths(self):
        invalid_values = [
            'not-a-list',
            ['/one', '/two', '/three', '/four'],
            ['https://example.com'],
            ['/inventory', 42],
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                response = self.client.patch(
                    '/api/auth/home/',
                    data=json.dumps({'pinnedPaths': value}),
                    content_type='application/json',
                )
                self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self):
        self.client.logout()
        response = self.client.get('/api/auth/home/')
        self.assertEqual(response.status_code, 401)
