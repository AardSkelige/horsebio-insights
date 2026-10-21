from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

import requests
from django.test import TestCase
from django.utils import timezone

from production_plan.models import WbOrder, WbSync
from production_plan.services import wb_sales

GET = 'production_plan.services.wb_sales.requests.get'
TODAY = date(2026, 10, 21)


def reply(status, body=None):
    return Mock(status_code=status, json=Mock(return_value=body), text='')


def order(srid, day='2026-09-15T10:00:00', article='11-36ap0100', cancel=False):
    return {'srid': srid, 'date': day, 'lastChangeDate': day, 'supplierArticle': article, 'isCancel': cancel}


@patch.dict('os.environ', {'WB_STATS_TOKEN': 'token'})
@patch('api.services.http_retry.time.sleep')
class WbSalesTests(TestCase):
    def test_keeps_orders_and_history_start(self, _sleep):
        with patch(GET, return_value=reply(200, [order('a'), order('b', cancel=True)])) as get:
            self.assertEqual(wb_sales.sync(TODAY), 2)
        self.assertEqual(get.call_args.kwargs['params']['dateFrom'], (TODAY - timedelta(days=89)).isoformat())
        self.assertEqual(WbOrder.objects.get(srid='a').article, '11-36AP0100')
        self.assertTrue(WbOrder.objects.get(srid='b').is_cancel)
        self.assertEqual(wb_sales.covered_from(), TODAY - timedelta(days=89))

    def test_repeat_updates_and_history_grows(self, _sleep):
        with patch(GET, return_value=reply(200, [order('a')])):
            wb_sales.sync(TODAY)
        with patch(GET, return_value=reply(200, [order('a', cancel=True)])):
            wb_sales.sync(TODAY + timedelta(days=1))
        self.assertEqual(WbOrder.objects.count(), 1)
        self.assertTrue(WbOrder.objects.get(srid='a').is_cancel)
        self.assertEqual(wb_sales.covered_from(), TODAY - timedelta(days=89))

    def test_gap_in_loading_restarts_history(self, _sleep):
        WbSync.objects.create(covered_from=date(2026, 1, 1))
        WbSync.objects.update(synced_at=timezone.make_aware(datetime(2026, 4, 1)))
        with patch(GET, return_value=reply(200, [])):
            wb_sales.sync(TODAY)
        self.assertEqual(wb_sales.covered_from(), TODAY - timedelta(days=89))

    def test_pages_by_last_change(self, _sleep):
        with patch.object(wb_sales, 'PAGE', 2), \
             patch(GET, side_effect=[reply(200, [order('a'), order('b', day='2026-09-20T08:00:00')]), reply(200, [order('c')])]) as get:
            self.assertEqual(wb_sales.sync(TODAY), 3)
        self.assertEqual(get.call_args.kwargs['params']['dateFrom'], '2026-09-20T08:00:00')

    def test_same_order_twice_in_one_answer(self, _sleep):
        with patch(GET, return_value=reply(200, [order('a'), order('a', cancel=True)])):
            wb_sales.sync(TODAY)
        self.assertTrue(WbOrder.objects.get(srid='a').is_cancel)

    def test_full_page_with_one_change_time_does_not_loop(self, _sleep):
        same = [order('a', day='2026-09-20T08:00:00'), order('b', day='2026-09-20T08:00:00')]
        with patch.object(wb_sales, 'PAGE', 2), \
             patch(GET, side_effect=[reply(200, same), reply(200, same), reply(200, same)]) as get:
            wb_sales.sync(TODAY)
        self.assertEqual(get.call_count, 2)

    def test_waits_out_limit_and_network(self, sleep):
        with patch(GET, side_effect=[reply(429), requests.ConnectionError('обрыв'), reply(200, [])]):
            wb_sales.sync(TODAY, wb_sales.QUICK_PAUSES)
        self.assertEqual(sleep.call_count, 2)

    def test_bad_token_is_a_clear_error(self, sleep):
        with patch(GET, return_value=reply(401)):
            with self.assertRaises(wb_sales.WbSalesError):
                wb_sales.sync(TODAY)
        sleep.assert_not_called()
