import os
import sys
from unittest import mock

from django.test import SimpleTestCase

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio',
                                '01_daemons', '03_returns', 'scripts'))

with mock.patch.dict(os.environ, {'MOYSKLAD_TOKEN': os.environ.get('MOYSKLAD_TOKEN') or 'test-token'}):
    import wb_returns  # noqa: E402

ROW = {'orderId': 101, 'shkId': 5, 'stickerId': '7', 'srid': 's', 'nmId': 12862181,
       'returnStatus': 'В пути в пвз', 'returnType': 'Возврат товара, который приехал по МП, продавцу',
       'dstOfficeAddress': 'Жуковский', 'subjectName': 'Гель', 'sku': '1680063403480',
       'orderDt': '2026-10-20', 'readyToReturnDt': None, 'completedDt': None, 'expiredDt': None}


def response(status, report=None):
    r = mock.Mock(status_code=status, headers={})
    r.json.return_value = {'count': len(report or []), 'report': report or []}
    r.raise_for_status = mock.Mock()
    return r


class NormalizeTests(SimpleTestCase):

    def test_reads_new_field_names(self):
        info = wb_returns._normalize(ROW)
        self.assertEqual(info['status'], 'В пути в пвз')
        self.assertEqual(info['barcode'], '1680063403480')
        self.assertTrue(wb_returns.needs_document(info))


class GetWindowTests(SimpleTestCase):

    def test_pages_until_short_page(self):
        pages = [response(200, [ROW] * 1000), response(200, [ROW] * 3)]
        with mock.patch.object(wb_returns._requests, 'get', side_effect=pages) as get:
            rows = wb_returns._get_window({}, '2026-10-04', '2026-11-03', 'active')
        self.assertEqual(len(rows), 1003)
        self.assertEqual([c.kwargs['params']['offset'] for c in get.call_args_list], [0, 1000])
        self.assertEqual(get.call_args_list[0].kwargs['params']['status'], 'active')

    def test_no_content_is_empty(self):
        with mock.patch.object(wb_returns._requests, 'get', return_value=response(204)):
            self.assertEqual(wb_returns._get_window({}, '2026-10-04', '2026-11-03', 'archive'), [])

    def test_rate_limit_to_the_end_is_an_error(self):
        with mock.patch.object(wb_returns._requests, 'get', return_value=response(429)), \
                mock.patch.object(wb_returns.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                wb_returns._get_window({}, '2026-10-04', '2026-11-03', 'active')


class FetchReturnsTests(SimpleTestCase):

    def test_asks_active_and_archive(self):
        seen = []

        def get(url, headers, params, timeout):
            seen.append(params['status'])
            return response(200, [{**ROW, 'orderId': len(seen)}])

        with mock.patch.dict(os.environ, {'WB_API_TOKEN': 't'}), \
                mock.patch.object(wb_returns._requests, 'get', side_effect=get), \
                mock.patch.object(wb_returns.time, 'sleep'):
            rows = wb_returns.fetch_returns(days_back=30)
        self.assertEqual(seen, ['active', 'archive'])
        self.assertEqual(len(rows), 2)
