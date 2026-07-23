from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from core.models import (
    Counterparty, Product, RawMaterial, Shipment, ShipmentItem, Supply, SupplyItem,
)


SCRIPT_ID = 'horsebio_buy_prices'


@override_settings(CRON_SECRET='test-cron-secret')
class ScriptsMutationAuthorizationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('user', password='password')
        self.admin = User.objects.create_superuser(
            'admin', email='admin@example.com', password='password'
        )

    def _post_mutating_endpoints(self, client, **headers):
        requests = [
            (f'/api/scripts/{SCRIPT_ID}/run/', {
                'api.views.scripts_monitor._is_running': False,
                'api.views.scripts_monitor.os.path.exists': True,
                'api.views.scripts_monitor._run_script_async': 'run-1',
            }),
            (f'/api/scripts/{SCRIPT_ID}/stop/', {}),
            (f'/api/scripts/{SCRIPT_ID}/runs/run-1/delete/', {
                'api.views.scripts_monitor._is_running': False,
                'api.views.scripts_monitor.os.path.exists': True,
                'api.views.scripts_monitor.os.unlink': None,
            }),
        ]
        responses = []
        for path, mocks in requests:
            with ExitStack() as stack:
                for target, return_value in mocks.items():
                    stack.enter_context(patch(target, return_value=return_value))
                responses.append(client.post(path, **headers))
        return responses

    def test_regular_user_cannot_run_stop_or_delete(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        responses = self._post_mutating_endpoints(client)

        self.assertEqual([response.status_code for response in responses], [403, 403, 403])

    def test_regular_user_keeps_read_only_access(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        with (
            patch('api.views.scripts_monitor._get_latest_run', return_value=None),
            patch('api.views.scripts_monitor._is_running', return_value=False),
            patch('api.views.scripts_monitor.os.path.exists', return_value=True),
        ):
            response = client.get('/api/scripts/')

        self.assertEqual(response.status_code, 200)

    def test_admin_session_requires_csrf_for_all_mutations(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)

        responses = self._post_mutating_endpoints(client)

        self.assertEqual([response.status_code for response in responses], [403, 403, 403])

    def test_admin_with_csrf_can_run_stop_and_delete(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        csrf_token = 'a' * 32
        client.cookies['csrftoken'] = csrf_token

        responses = self._post_mutating_endpoints(
            client, HTTP_X_CSRFTOKEN=csrf_token
        )

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])

    def test_cron_secret_can_mutate_without_browser_csrf(self):
        client = Client(enforce_csrf_checks=True)

        responses = self._post_mutating_endpoints(
            client, HTTP_X_CRON_SECRET='test-cron-secret'
        )

        self.assertEqual([response.status_code for response in responses], [200, 200, 200])


class AnalyticsListValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('user', password='password')
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(self.user)
        self.client.force_login(self.user)

    def test_invalid_pagination_is_rejected_consistently(self):
        cases = [
            ('/api/products/', 'page=not-a-number'),
            ('/api/counterparties/', 'page=0'),
            ('/api/supplies/materials/list/', 'pageSize=501'),
            ('/api/supplies/suppliers/', 'pageSize=0'),
        ]

        for path, query in cases:
            with self.subTest(path=path, query=query):
                response = self.client.get(f'{path}?{query}')
                self.assertEqual(response.status_code, 400)

    def test_invalid_dates_and_ranges_are_rejected(self):
        cases = [
            ('/api/products/', 'startDate=not-a-date'),
            ('/api/counterparties/', 'startDate=2025-02-01&endDate=2025-01-01'),
            ('/api/supplies/materials/list/', 'endDate=31-01-2025'),
            ('/api/supplies/suppliers/', 'startDate=2025-02-01&endDate=2025-01-01'),
        ]

        for path, query in cases:
            with self.subTest(path=path, query=query):
                response = self.client.get(f'{path}?{query}')
                self.assertEqual(response.status_code, 400)

    def test_unknown_sort_fields_are_rejected(self):
        for path in (
            '/api/products/',
            '/api/counterparties/',
            '/api/supplies/materials/list/',
            '/api/supplies/suppliers/',
        ):
            with self.subTest(path=path):
                response = self.client.get(f'{path}?sortField=not_a_real_column')
                self.assertEqual(response.status_code, 400)

    def test_search_treats_regex_characters_as_plain_text(self):
        counterparty = Counterparty.objects.create(
            name='Покупатель [тест]', external_id='counterparty-1'
        )
        product = Product.objects.create(
            name='Товар [тест]', external_id='product-1',
            group='Товары', subgroup='Группа'
        )
        shipment = Shipment.objects.create(
            counterparty=counterparty,
            external_id='shipment-1',
            number='1',
            date=timezone.now(),
        )
        ShipmentItem.objects.create(
            shipment=shipment, product=product, quantity=1, price=1
        )
        material = RawMaterial.objects.create(
            name='Материал [тест]', external_id='material-1', group='Тара'
        )
        supply = Supply.objects.create(
            counterparty=counterparty,
            external_id='supply-1',
            number='1',
            date=timezone.now(),
            sum=Decimal('1'),
        )
        SupplyItem.objects.create(
            supply=supply,
            raw_material=material,
            quantity=Decimal('1'),
            price=Decimal('1'),
            total=Decimal('1'),
        )

        product_response = self.client.get('/api/products/?search=%5B')
        counterparty_response = self.client.get('/api/counterparties/?search=%5B')
        material_response = self.client.get('/api/supplies/materials/list/?search=%5B')
        supplier_response = self.client.get('/api/supplies/suppliers/?search=%5B')

        self.assertEqual(product_response.status_code, 200)
        self.assertEqual(counterparty_response.status_code, 200)
        self.assertEqual(material_response.status_code, 200)
        self.assertEqual(supplier_response.status_code, 200)
        self.assertEqual(product_response.json()['data']['total'], 1)
        self.assertEqual(counterparty_response.json()['data']['total'], 1)
        self.assertEqual(material_response.json()['data']['total'], 1)
        self.assertEqual(supplier_response.json()['data']['total'], 1)
