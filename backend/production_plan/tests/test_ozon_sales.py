from datetime import date
from unittest.mock import Mock, patch

import requests

from django.test import TestCase

from api.services.ozon_stock import OzonStockError
from production_plan.models import OzonMonthSales
from production_plan.services import ozon_sales

POST = 'api.services.ozon_stock.requests.post'
HEADERS = 'api.services.ozon_stock._headers'


def reply(status, body=None):
    return Mock(status_code=status, json=Mock(return_value=body or {}), text='')


ANALYTICS = {'result': {'data': [
    {'dimensions': [{'id': '111'}], 'metrics': [32, 2]},
    {'dimensions': [{'id': '222'}], 'metrics': [5, 0]},
    {'dimensions': [{'id': '999'}], 'metrics': [4, 0]},
]}}
INFO = {'items': [
    {'offer_id': '11-36ap0100', 'sources': [{'sku': 111}, {'sku': 222}]},
]}


@patch(HEADERS, return_value={})
@patch('api.services.http_retry.time.sleep')
class OzonSalesTests(TestCase):
    def test_sums_skus_of_one_article(self, _sleep, _headers):
        with patch(POST, side_effect=[reply(200, ANALYTICS), reply(200, INFO)]) as post:
            total = ozon_sales.sync_month(date(2026, 9, 1))
        self.assertEqual(total, 35)
        self.assertEqual(post.call_args_list[0].kwargs['json']['date_to'], '2026-09-30')
        self.assertEqual(list(OzonMonthSales.objects.values_list('article', 'quantity')), [('11-36AP0100', 35)])

    def test_resync_replaces_the_month(self, _sleep, _headers):
        OzonMonthSales.objects.create(month=date(2026, 9, 1), article='OLD', quantity=1)
        with patch(POST, side_effect=[reply(200, ANALYTICS), reply(200, INFO)]):
            ozon_sales.sync_month(date(2026, 9, 1))
        self.assertFalse(OzonMonthSales.objects.filter(article='OLD').exists())

    def test_waits_out_the_rate_limit_and_busy_server(self, sleep, _headers):
        with patch(POST, side_effect=[reply(429), reply(500), reply(200, ANALYTICS), reply(200, INFO)]):
            self.assertEqual(ozon_sales.sync_month(date(2026, 9, 1)), 35)
        self.assertEqual(sleep.call_count, 2)

    def test_gives_up_after_retries(self, _sleep, _headers):
        with patch(POST, return_value=reply(500)):
            with self.assertRaises(OzonStockError):
                ozon_sales.sync_month(date(2026, 9, 1))

    def test_network_error_is_retried(self, sleep, _headers):
        with patch(POST, side_effect=[requests.ConnectionError('обрыв'), reply(200, ANALYTICS), reply(200, INFO)]):
            self.assertEqual(ozon_sales.sync_month(date(2026, 9, 1)), 35)

    def test_bad_request_is_not_retried(self, sleep, _headers):
        with patch(POST, return_value=reply(400)):
            with self.assertRaises(OzonStockError):
                ozon_sales.sync_month(date(2026, 9, 1))
        sleep.assert_not_called()

    def test_unexpected_answer_is_a_clear_error(self, _sleep, _headers):
        with patch(POST, return_value=reply(200, {'error': 'что-то'})):
            with self.assertRaisesMessage(OzonStockError, 'неожиданный ответ'):
                ozon_sales.sync_month(date(2026, 9, 1))
