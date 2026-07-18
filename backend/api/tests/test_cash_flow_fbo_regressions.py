import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase

from api.services.cash_flow import _fetch_operation_pages
from api.views.fbo import get_stock_info


class CashFlowPaginationRegressionTests(SimpleTestCase):
    @patch('api.services.cash_flow.requests.get')
    def test_page_error_is_raised_instead_of_returning_partial_operations(self, mock_get):
        first_page = MagicMock()
        first_page.json.return_value = {'rows': [{'id': str(i)} for i in range(1000)]}

        failed_page = MagicMock()
        failed_page.raise_for_status.side_effect = requests.HTTPError('MoySklad error')
        mock_get.side_effect = [first_page, failed_page]

        with self.assertRaises(requests.HTTPError):
            _fetch_operation_pages(
                'paymentin',
                '2024-01-01 00:00:00',
                '2024-01-31 23:59:59',
                {'Authorization': 'Bearer token'},
            )


class CashFlowEndpointRegressionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='cash-flow-user', password='password')
        self.client.login(username='cash-flow-user', password='password')

    @patch('api.views.cash_flow.get_operations_data', side_effect=requests.Timeout('timeout'))
    def test_external_operation_error_does_not_return_success(self, mock_operations):
        response = self.client.post(
            '/api/analysis/cash-flow/',
            data=json.dumps({
                'date_from': '2024-01-01T00:00:00',
                'date_to': '2024-01-31T23:59:59',
            }),
            content_type='application/json',
            secure=True,
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()['code'], 'EXTERNAL_SERVICE_ERROR')
        self.assertNotIn('success', response.json())


class FBOStockRegressionTests(SimpleTestCase):
    @patch('api.views.fbo.requests.get')
    def test_batch_error_is_raised_instead_of_turning_all_stock_into_zero(self, mock_get):
        first_batch = MagicMock()
        first_batch.json.return_value = {
            'rows': [{
                'meta': {'href': 'https://example.test/entity/product/0'},
                'stock': 7,
                'quantity': 7,
            }]
        }

        failed_batch = MagicMock()
        failed_batch.raise_for_status.side_effect = requests.HTTPError('MoySklad error')
        mock_get.side_effect = [first_batch, failed_batch]

        client = SimpleNamespace(BASE_URL='https://example.test', headers={})
        assortments = [f'https://example.test/entity/product/{i}' for i in range(11)]

        with self.assertRaises(requests.HTTPError):
            get_stock_info(client, assortments)
