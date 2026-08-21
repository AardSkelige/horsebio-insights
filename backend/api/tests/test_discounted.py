"""Тесты страницы «Уценка».

Главное, что здесь проверяется: позиция уходит в «пора снимать» ровно за два
месяца до конца срока годности, а строки сортируются так, чтобы то, с чем надо
что-то делать, было сверху. Дата «годен до» проставляется человеком в карточке,
поэтому отдельно проверяется случай, когда её забыли заполнить.
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase

from api.access import page_keys_for_path
from api.models import UserPageAccess
from api.views.discounted import (
    STATE_DELIST, STATE_EXPIRED, STATE_NO_DATE, STATE_OK, _build_data, _state_of,
)

STORE_HREF = 'https://api.moysklad.ru/api/remap/1.2/entity/store/store-uc'
FOLDER_HREF = 'https://api.moysklad.ru/api/remap/1.2/entity/productfolder/folder-uc'
ATTR_ID = 'attr-godendo'

RETAIL = 'Розница – ИП (Сайт | РРЦ)'


def _product(pid, article, name, expires):
    """Карточка уценённого товара. Цена уже уценённая — 70 % от розничной."""
    attributes = [{'id': ATTR_ID, 'name': 'Годен до', 'value': f'{expires} 00:00:00.000'}] if expires else []
    return {
        'id': pid,
        'article': article,
        'name': name,
        'attributes': attributes,
        'salePrices': [{'priceType': {'name': RETAIL}, 'value': 168000}],  # 1680 ₽
    }


def _stock(pid, quantity, cost_kopecks):
    return {
        'meta': {'href': f'https://api.moysklad.ru/api/remap/1.2/entity/product/{pid}'},
        'stock': quantity,
        'reserve': 0.0,
        'price': cost_kopecks,
    }


class StateTest(SimpleTestCase):
    """Правило «снимаем за 2 месяца» — граница и то, что по обе стороны от неё."""

    def test_ok_while_more_than_two_months_left(self):
        self.assertEqual(_state_of(date(2027, 1, 1), 61), STATE_OK)

    def test_delist_exactly_at_two_months(self):
        self.assertEqual(_state_of(date(2026, 10, 20), 60), STATE_DELIST)

    def test_delist_when_less_than_two_months(self):
        self.assertEqual(_state_of(date(2026, 9, 1), 11), STATE_DELIST)

    def test_expired_when_date_passed(self):
        self.assertEqual(_state_of(date(2026, 8, 1), -20), STATE_EXPIRED)

    def test_no_date_when_attribute_empty(self):
        self.assertEqual(_state_of(None, 0), STATE_NO_DATE)


class BuildDataTest(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.today = date.today()

    def tearDown(self):
        cache.clear()

    def _run(self, products, stock_rows, days_on_stock=None):
        with patch('api.views.discounted._resolve_refs', return_value=(STORE_HREF, FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=[products, stock_rows]), \
             patch('api.views.discounted._days_on_stock', return_value=days_on_stock):
            return _build_data()

    def test_counts_only_positions_with_stock(self):
        """Карточка без остатка в сводку не идёт — товар уже продан или ещё не пришёл."""
        soon = (self.today + timedelta(days=100)).isoformat()
        data = self._run(
            [_product('p1', '01-01AP0500-UC', 'Уценка Хондро', soon),
             _product('p2', '01-02AP0500-UC', 'Уценка Джуниор', soon)],
            [_stock('p1', 4.0, 35000)],
        )
        self.assertEqual(data['summary']['positions'], 1)
        self.assertEqual(data['summary']['units'], 4.0)
        self.assertEqual(data['summary']['sum'], 6720.0)      # 1680 × 4
        self.assertEqual(data['summary']['sum_cost'], 1400.0)  # 350 × 4

    def test_restores_price_before_discount(self):
        """На сайте рядом с ценой уценки показываем зачёркнутую обычную — 1680 / 0,7."""
        data = self._run(
            [_product('p1', '01-01AP0500-UC', 'Уценка Хондро', (self.today + timedelta(days=100)).isoformat())],
            [_stock('p1', 1.0, 35000)],
        )
        self.assertEqual(data['positions'][0]['price'], 1680.0)
        self.assertEqual(data['positions'][0]['price_full'], 2400.0)

    def test_urgent_rows_come_first(self):
        """Истёкшее, затем «пора снимать», затем без даты, затем спокойные."""
        data = self._run(
            [
                _product('ok', 'A-UC', 'Спокойная', (self.today + timedelta(days=200)).isoformat()),
                _product('nd', 'B-UC', 'Без даты', None),
                _product('dl', 'C-UC', 'Пора снимать', (self.today + timedelta(days=30)).isoformat()),
                _product('ex', 'D-UC', 'Истекла', (self.today - timedelta(days=5)).isoformat()),
            ],
            [_stock(pid, 1.0, 10000) for pid in ('ok', 'nd', 'dl', 'ex')],
        )
        self.assertEqual([p['state'] for p in data['positions']],
                         [STATE_EXPIRED, STATE_DELIST, STATE_NO_DATE, STATE_OK])
        self.assertEqual(data['summary']['needs_action'], 3)

    def test_missing_expiry_does_not_break_the_page(self):
        """Дату забыли проставить — строка остаётся видимой и помечается, а не исчезает."""
        data = self._run(
            [_product('p1', 'A-UC', 'Без даты', None)],
            [_stock('p1', 2.0, 10000)],
        )
        row = data['positions'][0]
        self.assertEqual(row['state'], STATE_NO_DATE)
        self.assertIsNone(row['expires'])
        self.assertIsNone(row['days_left'])

    def test_days_on_stock_only_for_positions_with_stock(self):
        """Отчёт по документам стоит запроса на товар — для пустых карточек не дёргаем."""
        soon = (self.today + timedelta(days=100)).isoformat()
        with patch('api.views.discounted._resolve_refs', return_value=(STORE_HREF, FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=[
                 [_product('p1', 'A-UC', 'С остатком', soon), _product('p2', 'B-UC', 'Пустая', soon)],
                 [_stock('p1', 3.0, 10000)],
             ]), \
             patch('api.views.discounted._days_on_stock', return_value=42) as days:
            data = _build_data()

        self.assertEqual(days.call_count, 1)
        by_article = {p['article']: p for p in data['positions']}
        self.assertEqual(by_article['A-UC']['days_on_stock'], 42)
        self.assertIsNone(by_article['B-UC']['days_on_stock'])


class AccessTest(TestCase):
    """Страница закрыта постраничным доступом — как и остальные разделы."""

    def setUp(self):
        cache.clear()
        self.client = Client()

    def tearDown(self):
        cache.clear()

    def test_path_belongs_to_the_page(self):
        self.assertIn('discounted', page_keys_for_path('/api/discounted/'))

    def test_user_without_access_is_rejected(self):
        User.objects.create_user('lera', password='secret')
        self.client.login(username='lera', password='secret')
        self.assertEqual(self.client.get('/api/discounted/').status_code, 403)

    def test_user_with_access_gets_data(self):
        user = User.objects.create_user('lera', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='lera', password='secret')

        with patch('api.views.discounted._build_data', return_value={'positions': [], 'summary': {}}):
            response = self.client.get('/api/discounted/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['positions'], [])


class DelistTest(TestCase):
    """Снятие с продажи: данные для обмена берём из МойСклад, а не из запроса."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='sergey', password='secret')

    def tearDown(self):
        cache.clear()

    def test_sends_exchange_with_fresh_product_data(self):
        with patch('api.views.discounted._get',
                   return_value={'article': 'A-UC', 'name': 'Уценка Хондро'}), \
             patch('api.views.discounted.site_exchange.set_visibility') as send:
            response = self.client.post('/api/discounted/p1/delist/')

        self.assertEqual(response.status_code, 200)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs['article'], 'A-UC')
        self.assertEqual(send.call_args.kwargs['visibility'], 1)  # недоступен (404)

    def test_exchange_failure_is_not_swallowed(self):
        """Молчаливый провал опаснее ошибки: человек решит, что товар снят."""
        from api.services.site_exchange import SiteExchangeError

        with patch('api.views.discounted._get',
                   return_value={'article': 'A-UC', 'name': 'Уценка Хондро'}), \
             patch('api.views.discounted.site_exchange.set_visibility',
                   side_effect=SiteExchangeError('сайт не ответил')):
            response = self.client.post('/api/discounted/p1/delist/')

        self.assertGreaterEqual(response.status_code, 400)


class RequestShapeTest(SimpleTestCase):
    """Форма запросов к МойСклад.

    /entity/product не умеет фильтровать по productFolder — отвечает 412
    «неизвестное поле фильтрации» (подтверждено документацией: у этого атрибута
    колонка «Фильтрация» пустая). Карточки ищем по pathName, и это ровно та
    ошибка, из-за которой страница один раз уже упала на проде.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_products_are_filtered_by_path_not_by_folder(self):
        calls = []

        def remember(path, params=None):
            calls.append((path, dict(params or {})))
            return []

        with patch('api.views.discounted._resolve_refs', return_value=(STORE_HREF, FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=remember):
            _build_data()

        product_call = next(c for c in calls if c[0] == '/entity/product')
        self.assertEqual(product_call[1]['filter'], 'pathName=Товары/Уценка')
        self.assertNotIn('productFolder', product_call[1]['filter'])

    def test_stock_report_asks_for_products_not_variants(self):
        """Без groupBy=product отчёт вернёт ссылки на модификации, и id не сойдутся."""
        calls = []

        def remember(path, params=None):
            calls.append((path, dict(params or {})))
            return []

        with patch('api.views.discounted._resolve_refs', return_value=(STORE_HREF, FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=remember):
            _build_data()

        stock_call = next(c for c in calls if c[0] == '/report/stock/all')
        self.assertEqual(stock_call[1]['groupBy'], 'product')
        self.assertIn(f'store={STORE_HREF}', stock_call[1]['filter'])
