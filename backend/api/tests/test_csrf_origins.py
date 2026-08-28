"""Регрессия: сайт работает по HTTPS, а доверенные источники были только http://.

Из-за этого Django отклонял любой небезопасный метод (PATCH/POST/DELETE)
с 403 «Origin checking failed»: страницы грузились, а сохранение молча падало.
"""

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

PROD_HOST = 'insight.horse-bio.ru'


class TrustedOriginsTests(TestCase):
    def test_prod_host_is_trusted_over_both_schemes(self):
        for origins in (settings.CSRF_TRUSTED_ORIGINS, settings.CORS_ALLOWED_ORIGINS):
            self.assertIn(f'https://{PROD_HOST}', origins)
            self.assertIn(f'http://{PROD_HOST}', origins)

    @override_settings(ALLOWED_HOSTS=[PROD_HOST], SECURE_SSL_REDIRECT=False)
    def test_https_origin_passes_csrf_check(self):
        user = User.objects.create_user('lilia', password='password')
        client = Client(enforce_csrf_checks=True, HTTP_HOST=PROD_HOST)
        client.force_login(user)
        client.get('/parser/csrf/')  # эндпоинт, из которого фронт берёт csrftoken

        response = client.patch(
            '/api/auth/home/',
            data='{"pinnedPaths": []}',
            content_type='application/json',
            HTTP_ORIGIN=f'https://{PROD_HOST}',
            HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value,
        )

        self.assertEqual(response.status_code, 200)
