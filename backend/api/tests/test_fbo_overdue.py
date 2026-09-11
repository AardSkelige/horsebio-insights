"""FBO: просроченные отгрузки и отбор предстоящих.

Раздел показывает предстоящие отгрузки, и это осознанно. Но 11.09.2026 он
показал пустую таблицу, хотя неотгруженными висели девять FBO-заказов на
2,4 млн — у всех плановая дата уже прошла. Пустота без пояснения читалась как
«всё отгружено».

Поэтому проверяем два свойства: просроченные считаются и попадают в сводку,
а отбор предстоящих не ограничен датой создания заказа (иначе заказ с давней
датой заведения выпадал бы, даже когда его отгрузка ещё впереди).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from api.views import fbo

STATE_HREF = 'https://api.moysklad.ru/api/remap/1.2/entity/customerorder/metadata/states/fbo-1'
CLIENT = SimpleNamespace(headers={'Authorization': 'Bearer x'},
                         BASE_URL='https://api.moysklad.ru/api/remap/1.2')
URL = f'{CLIENT.BASE_URL}/entity/customerorder'


def _page(rows):
    response = MagicMock()
    response.json.return_value = {'rows': rows}
    return response


def _order(planned, shipped_sum, total_sum):
    return {'name': 'test', 'deliveryPlannedMoment': planned,
            'shippedSum': shipped_sum, 'sum': total_sum}


class OverdueCountTests(SimpleTestCase):
    def setUp(self):
        self.today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    def overdue(self, rows):
        with patch('api.views.fbo.ms_http.get', return_value=_page(rows)):
            return fbo._overdue_fbo_orders(CLIENT, URL, STATE_HREF, self.today)

    def test_only_unshipped_orders_are_counted(self):
        """Отгруженный заказ просроченным не считается, даже если дата прошла."""
        result = self.overdue([
            _order('2026-09-02 12:00:00.000', 0, 100000),
            _order('2026-09-03 12:00:00.000', 55500, 100000),
        ])
        self.assertEqual(result['count'], 1)

    def test_sum_is_reported_in_roubles(self):
        """МойСклад хранит суммы в копейках, наружу отдаём рубли."""
        result = self.overdue([
            _order('2026-09-02 12:00:00.000', 0, 25496500),
            _order('2026-09-03 12:00:00.000', 0, 19136000),
        ])
        self.assertEqual(result['sum'], 446325.0)

    def test_oldest_is_measured_in_days(self):
        """Самый давний нужен, чтобы отличить вчерашнюю просрочку от годовой."""
        long_ago = (self.today - timezone.timedelta(days=595)).strftime('%Y-%m-%d %H:%M:%S.000')
        yesterday = (self.today - timezone.timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S.000')
        result = self.overdue([
            _order(yesterday, 0, 100000),
            _order(long_ago, 0, 100000),
        ])
        self.assertEqual(result['oldest_days'], 595)

    def test_nothing_overdue_gives_zeroes(self):
        result = self.overdue([])
        self.assertEqual((result['count'], result['sum'], result['oldest_days']), (0, 0, 0))

    def test_orders_are_requested_by_state_and_past_date(self):
        """Спрашиваем у МойСклада ровно просроченные, а не всё подряд."""
        with patch('api.views.fbo.ms_http.get', return_value=_page([])) as get:
            fbo._overdue_fbo_orders(CLIENT, URL, STATE_HREF, self.today)

        sent = get.call_args.kwargs['params']['filter']
        self.assertIn(f'state={STATE_HREF}', sent)
        self.assertIn('deliveryPlannedMoment<', sent)
        self.assertNotIn('moment>=', sent)


class UpcomingFilterTests(TestCase):
    """Отбор предстоящих не ограничен датой создания заказа.

    База нужна: сборка попутно считает продажи за тридцать дней по отгрузкам.
    """

    def test_filter_has_no_creation_window(self):
        captured = []

        def fake_get(url, **kwargs):
            captured.append(kwargs.get('params', {}).get('filter', ''))
            return _page([])

        with patch('api.views.fbo.ms_http.get', side_effect=fake_get), \
                patch('api.views.fbo.get_fbo_state_href', return_value=STATE_HREF), \
                patch('api.views.fbo.MoySkladAPIClient', return_value=CLIENT), \
                patch('api.views.fbo.get_stock_info', return_value={}):
            fbo._build_fbo_analysis_data()

        upcoming = next(f for f in captured if 'deliveryPlannedMoment>=' in f)
        # Окно по дате создания отсекало заказ, заведённый давно, но ждущий
        # отгрузки впереди. Такой заказ разделу нужен.
        self.assertNotIn('moment>=', upcoming)
        self.assertIn(f'state={STATE_HREF}', upcoming)
