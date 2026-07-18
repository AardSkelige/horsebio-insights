import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings

from ozon import views


OZON_POST_URLS = (
    '/api/ozon/report/',
    '/api/ozon/competitors/process/',
    '/api/ozon/stock/process/',
    '/api/ozon/fbo-converter/convert/',
)


@override_settings(SECURE_SSL_REDIRECT=False)
class OzonEndpointSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ozon-user', password='test-password'
        )

    def test_mutating_endpoints_require_authentication(self):
        client = Client()

        for url in OZON_POST_URLS:
            with self.subTest(url=url):
                response = client.post(url)
                self.assertEqual(response.status_code, 401)

    def test_mutating_endpoints_require_csrf_for_session_user(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        for url in OZON_POST_URLS:
            with self.subTest(url=url):
                response = client.post(url)
                self.assertEqual(response.status_code, 403)

    def test_mutating_endpoints_accept_valid_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        csrf_response = client.get('/parser/csrf/')
        csrf_token = csrf_response.json()['csrfToken']

        for url in OZON_POST_URLS:
            with self.subTest(url=url):
                response = client.post(url, HTTP_X_CSRFTOKEN=csrf_token)
                # No file is deliberately supplied: a 400 response confirms that
                # authentication and CSRF checks passed and the endpoint ran.
                self.assertEqual(response.status_code, 400)


@override_settings(SECURE_SSL_REDIRECT=False)
class OzonTemporaryFileTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='ozon-file-user', password='test-password'
        )
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        csrf_response = self.client.get('/parser/csrf/')
        self.csrf_token = csrf_response.json()['csrfToken']

    @staticmethod
    def _upload():
        return SimpleUploadedFile(
            'input.xlsx',
            b'test excel content',
            content_type=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )

    def _post_file(self, url):
        return self.client.post(
            url,
            {'file': self._upload()},
            HTTP_X_CSRFTOKEN=self.csrf_token,
        )

    def test_temp_paths_are_unique_even_when_files_exist_concurrently(self):
        first_path = None
        second_path = None
        try:
            first_path = views._save_uploaded_file(
                self._upload(), prefix='ozon_test_'
            )
            second_path = views._save_uploaded_file(
                self._upload(), prefix='ozon_test_'
            )

            self.assertNotEqual(first_path, second_path)
            self.assertTrue(os.path.isfile(first_path))
            self.assertTrue(os.path.isfile(second_path))
        finally:
            views._delete_temp_file(first_path)
            views._delete_temp_file(second_path)

    def test_temp_files_are_deleted_after_success(self):
        cases = (
            (
                '/api/ozon/competitors/process/',
                'ozon.services.competitors_analyzer.process_ozon_data',
            ),
            (
                '/api/ozon/stock/process/',
                'ozon.services.stock_analyzer.process_availability_data',
            ),
        )

        for url, processor_path in cases:
            captured_paths = []

            def process(path):
                captured_paths.append(path)
                self.assertTrue(os.path.isfile(path))
                return b'generated workbook'

            with self.subTest(url=url), patch(
                processor_path, side_effect=process
            ):
                response = self._post_file(url)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(captured_paths), 1)
            self.assertFalse(os.path.exists(captured_paths[0]))

    def test_temp_files_are_deleted_and_errors_are_sanitized(self):
        cases = (
            (
                '/api/ozon/competitors/process/',
                'ozon.services.competitors_analyzer.process_ozon_data',
            ),
            (
                '/api/ozon/stock/process/',
                'ozon.services.stock_analyzer.process_availability_data',
            ),
        )

        for url, processor_path in cases:
            captured_paths = []

            def fail(path):
                captured_paths.append(path)
                self.assertTrue(os.path.isfile(path))
                raise RuntimeError('secret backend detail')

            with self.subTest(url=url), patch(
                processor_path, side_effect=fail
            ):
                response = self._post_file(url)

            self.assertEqual(response.status_code, 500)
            self.assertEqual(
                response.json()['message'], views.INTERNAL_ERROR_MESSAGE
            )
            self.assertNotIn('secret backend detail', response.content.decode())
            self.assertEqual(len(captured_paths), 1)
            self.assertFalse(os.path.exists(captured_paths[0]))
