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
        'meta': {'uuidHref': f'https://online.moysklad.ru/app/#good/edit?id=ui-{pid}'},
    }


def _stock(pid, quantity, cost_kopecks):
    return {
        'meta': {'href': f'https://api.moysklad.ru/api/remap/1.2/entity/product/{pid}'},
        'stock': quantity,
        'reserve': 0.0,
        'price': cost_kopecks,
    }


def _operation(doc_type, quantity, cost_kopecks, doc_id='doc'):
    """Строка отчёта «Обороты по операциям»: приход в плюс, расход в минус."""
    return {
        'operation': {
            'meta': {
                'href': f'https://api.moysklad.ru/api/remap/1.2/entity/{doc_type}/{doc_id}',
                'type': doc_type,
            },
            'name': doc_id,
        },
        'quantity': quantity,
        'sum': cost_kopecks,
    }


def _document(doc_id, positions):
    """Документ продажи с позициями (id товара, количество, цена, скидка %)."""
    return {
        'id': doc_id,
        'positions': {
            'meta': {'size': len(positions)},
            'rows': [
                {
                    'assortment': {'meta': {'href': f'https://api.moysklad.ru/api/remap/1.2/entity/product/{pid}'}},
                    'quantity': quantity,
                    'price': price,
                    'discount': position[3] if len(position) > 3 else 0.0,
                }
                for position in positions
                for pid, quantity, price in [position[:3]]
            ],
        },
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
        # Аналитика за период проверяется отдельно (AnalyticsTest) и ходит в свои
        # отчёты — здесь она только мешала бы считать вызовы
        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=[products, stock_rows]), \
             patch('api.views.discounted._build_analytics', return_value={}), \
             patch('api.views.discounted.site_feed.offers', return_value={}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
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
        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted.site_feed.offers', return_value={}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
             patch('api.views.discounted._get_all_pages', side_effect=[
                 [_product('p1', 'A-UC', 'С остатком', soon), _product('p2', 'B-UC', 'Пустая', soon)],
                 [_stock('p1', 3.0, 10000)],
             ]), \
             patch('api.views.discounted._build_analytics', return_value={}), \
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

        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._build_analytics', return_value={}), \
             patch('api.views.discounted.site_feed.offers', return_value={}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
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

        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._build_analytics', return_value={}), \
             patch('api.views.discounted.site_feed.offers', return_value={}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
             patch('api.views.discounted._get_all_pages', side_effect=remember):
            _build_data()

        stock_call = next(c for c in calls if c[0] == '/report/stock/all')
        self.assertEqual(stock_call[1]['groupBy'], 'product')
        # Остаток считаем по всем складам: уценка лежит на складе готовой продукции
        # вместе с обычным товаром, отделяет её карточка, а не склад
        self.assertNotIn('store=', stock_call[1]['filter'])
        self.assertIn(f'productFolder={FOLDER_HREF}', stock_call[1]['filter'])


class AnalyticsTest(SimpleTestCase):
    """Итоги за период: уценено, продано, списано.

    Считаются по обороту в разрезе операций, где у каждой строки виден тип
    документа. Главное, что здесь проверяется: продажа опознаётся по документу,
    а не вычитанием из расхода, — иначе отгрузка комиссионеру (Ozon) уезжает
    в «списано». Плюс: перемещения не движение товара, возврат не удваивает
    продажу, выручка берётся из позиций документа.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _run(self, operations, documents=()):
        """operations — строки отчёта по операциям, documents — сами документы.

        Документы отдаём по тому же фильтру, что и МойСклад: только те, чьи id
        спрошены, — иначе продажа и возврат достались бы обоим запросам сразу.
        """
        from api.views.discounted import _build_analytics
        by_id = {d['id']: d for d in documents}

        def fetch(path, params=None):
            asked = [f.split('=', 1)[1] for f in (params or {}).get('filter', '').split(';') if f]
            return {'rows': [by_id[i] for i in asked if i in by_id]}

        with patch('api.views.discounted._get_all_pages', return_value=list(operations)), \
             patch('api.views.discounted._get', side_effect=fetch):
            return _build_analytics(['p1'], 365)

    def test_marked_is_income_of_the_processing(self):
        data = self._run([_operation('processing', 30.0, 900000)])
        self.assertEqual(data['marked']['quantity'], 30.0)
        self.assertEqual(data['marked']['cost'], 9000.0)

    def test_sale_is_taken_from_the_document_not_from_the_profit_report(self):
        """Отгрузка комиссионеру — продажа: отчёт прибыли её ещё не видит."""
        data = self._run(
            [_operation('processing', 30.0, 900000), _operation('demand', -2.0, -60000, 'd1')],
            [_document('d1', [('p1', 2.0, 230000)])],
        )
        self.assertEqual(data['sold']['quantity'], 2.0)
        self.assertEqual(data['sold']['revenue'], 4600.0)
        self.assertEqual(data['sold']['cost'], 600.0)
        self.assertEqual(data['written_off']['quantity'], 0)

    def test_write_off_is_a_document_not_the_remainder(self):
        data = self._run(
            [_operation('processing', 10.0, 300000), _operation('loss', -3.0, -90000)],
        )
        self.assertEqual(data['written_off']['quantity'], 3.0)
        self.assertEqual(data['written_off']['cost'], 900.0)
        self.assertEqual(data['sold']['quantity'], 0)

    def test_transfers_are_not_a_movement(self):
        """Перемещение между складами — не приход и не расход уценки."""
        data = self._run(
            [_operation('processing', 10.0, 300000),
             _operation('move', -10.0, -300000), _operation('move', 10.0, 300000)],
        )
        self.assertEqual(data['marked']['quantity'], 10.0)
        self.assertEqual(data['written_off']['quantity'], 0)

    def test_returns_do_not_inflate_sales(self):
        """Вернувшийся товар не должен считаться проданным."""
        data = self._run(
            [_operation('demand', -5.0, -150000, 'd1'), _operation('salesreturn', 2.0, 60000, 'r1')],
            [_document('d1', [('p1', 5.0, 168000)]), _document('r1', [('p1', 2.0, 168000)])],
        )
        self.assertEqual(data['sold']['quantity'], 3.0)
        self.assertEqual(data['sold']['cost'], 900.0)

    def test_revenue_ignores_other_goods_in_the_same_document(self):
        """В отгрузке рядом с уценкой едет обычный товар — он не наша выручка."""
        data = self._run(
            [_operation('demand', -1.0, -30000, 'd1')],
            [_document('d1', [('p1', 1.0, 168000), ('other', 3.0, 500000)])],
        )
        self.assertEqual(data['sold']['revenue'], 1680.0)

    def test_discount_in_the_position_lowers_revenue(self):
        data = self._run(
            [_operation('demand', -1.0, -30000, 'd1')],
            [_document('d1', [('p1', 1.0, 200000, 10.0)])],
        )
        self.assertEqual(data['sold']['revenue'], 1800.0)

    def test_empty_store_gives_zeros_not_errors(self):
        data = self._run([])
        self.assertEqual(data['marked']['quantity'], 0)
        self.assertEqual(data['sold']['revenue'], 0)
        self.assertEqual(data['written_off']['quantity'], 0)


class SiteStateTest(SimpleTestCase):
    """Публикация на сайте: читаем её из фида, а не угадываем.

    Важно различать «карточки на сайте нет» и «не смогли проверить»: в первом
    случае интерфейс предлагает опубликовать, во втором — молчит, иначе человек
    отправит карточку второй раз из-за упавшего фида.
    """

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _run(self, products, stock_rows, on_site):
        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=[products, stock_rows]), \
             patch('api.views.discounted._build_analytics', return_value={}), \
             patch('api.views.discounted.site_feed.offers', **on_site), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
             patch('api.views.discounted._days_on_stock', return_value=None):
            return _build_data()

    def _position(self, on_site):
        expires = (date.today() + timedelta(days=100)).isoformat()
        data = self._run(
            [_product('p1', '01-01AP0500-UC', 'Уценка // Хондро', expires)],
            [_stock('p1', 5.0, 30000)],
            on_site,
        )
        return data['positions'][0]

    def test_published_when_feed_knows_the_article(self):
        position = self._position({'return_value': {
            '01-01AP0500-UC': {'name': 'Уценка // Хондро',
                               'url': 'https://horse-bio.ru/ucenka-hondro',
                               'price': 1176.0, 'amount': 5.0, 'pictures': []},
        }})
        self.assertIs(position['published'], True)
        self.assertEqual(position['site_price'], 1176.0)
        self.assertEqual(position['site_quantity'], 5.0)
        self.assertEqual(position['site_url'], 'https://horse-bio.ru/ucenka-hondro')

    def test_not_published_when_feed_has_no_article(self):
        position = self._position({'return_value': {}})
        self.assertIs(position['published'], False)
        # без карточки на сайте адрес всё равно нужен — по нему её и откроют после публикации
        self.assertEqual(position['site_url'], 'https://horse-bio.ru/ucenka-hondro')

    def test_unknown_when_feed_is_down(self):
        position = self._position({'side_effect': RuntimeError('фид не ответил')})
        self.assertIsNone(position['published'])


class SlugTest(SimpleTestCase):
    """ЧПУ считается из названия — тем же правилом, что ставится в карточке сайта."""

    def test_transliterates_and_drops_separators(self):
        from api.views.discounted import site_slug
        self.assertEqual(
            site_slug('Уценка // Пробиотик GastroPro для лошадей, 1600г'),
            'ucenka-probiotik-gastropro-dlya-loshadej-1600g',
        )


class PublishTest(TestCase):
    """Отправка карточки на сайт."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='sergey', password='secret')

    def tearDown(self):
        cache.clear()

    def _post(self, product, pictures=('https://horse-bio.ru/d/a.png',), stock=7.0, on_site=None):
        with patch('api.views.discounted._get', return_value=product), \
             patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', return_value=[{'stock': stock}]), \
             patch('api.views.discounted.site_feed.offers', return_value=on_site or {}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
             patch('api.views.discounted.site_feed.pictures_for', return_value=list(pictures)) as pics, \
             patch('api.views.discounted.site_exchange.publish', return_value=len(pictures)) as publish:
            response = self.client.post('/api/discounted/p1/publish/')
        return response, publish, pics

    def test_publishes_with_stock_and_pictures_of_the_source_card(self):
        product = {
            'article': '01-01AP0500-UC',
            'name': 'Уценка // Хондро',
            'salePrices': [{'priceType': {'name': RETAIL}, 'value': 117600}],
        }
        response, publish, pics = self._post(product)

        self.assertEqual(response.status_code, 200)
        # фотографии берём у основной карточки — это артикул без суффикса
        pics.assert_called_once_with('01-01AP0500')
        kwargs = publish.call_args.kwargs
        self.assertEqual(kwargs['price'], 1176)
        self.assertEqual(kwargs['quantity'], 7)
        self.assertEqual(kwargs['pictures'], ['https://horse-bio.ru/d/a.png'])
        attributes = dict(kwargs['attributes'])
        self.assertEqual(attributes['ЧПУ'], 'ucenka-hondro')
        self.assertEqual(attributes['Товар уже со скидкой'], 1)
        self.assertEqual(attributes['Запретить индексацию страницы'], 1)

    def test_refuses_card_without_price(self):
        """Карточка без цены уехала бы на сайт с нулём — это хуже, чем ошибка."""
        product = {'article': '01-01AP0500-UC', 'name': 'Уценка // Хондро', 'salePrices': []}
        with patch('api.views.discounted._get', return_value=product), \
             patch('api.views.discounted.site_exchange.publish') as publish:
            response = self.client.post('/api/discounted/p1/publish/')

        self.assertGreaterEqual(response.status_code, 400)
        publish.assert_not_called()

    def test_new_card_is_created_hidden(self):
        """Новую карточку открывает человек, проверив её глазами."""
        product = {
            'article': '01-01AP0500-UC',
            'name': 'Уценка // Хондро',
            'salePrices': [{'priceType': {'name': RETAIL}, 'value': 117600}],
        }
        _, publish, _ = self._post(product)
        self.assertEqual(publish.call_args.kwargs['visibility'], 1)  # недоступен (404)

    def test_update_does_not_touch_visibility_of_a_live_card(self):
        """Повторная отправка не должна снимать товар с продажи."""
        product = {
            'article': '01-01AP0500-UC',
            'name': 'Уценка // Хондро',
            'salePrices': [{'priceType': {'name': RETAIL}, 'value': 117600}],
        }
        _, publish, _ = self._post(product, on_site={'01-01AP0500-UC': {'pictures': []}})
        self.assertIsNone(publish.call_args.kwargs['visibility'])

    def test_keywords_are_never_empty(self):
        """Пустое значение обмен не применяет — в карточке осталось бы старое."""
        product = {
            'article': '01-01AP0500-UC',
            'name': 'Уценка // Хондро',
            'salePrices': [{'priceType': {'name': RETAIL}, 'value': 117600}],
        }
        _, publish, _ = self._post(product)
        keywords = dict(publish.call_args.kwargs['attributes'])['Ключевые слова (Keywords)']
        self.assertTrue(keywords.strip())
        self.assertIn('хондро', keywords)


class CsvExportTest(TestCase):
    """Файл импорта — запасной путь, когда обмен упёрся в демо-лимит."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='sergey', password='secret')

    def tearDown(self):
        cache.clear()

    def _get(self, positions, description='<p>Текст основной карточки</p>',
             fields=None):
        fields = {'sostav': '<h3>Состав</h3><ul><li>Лён</li></ul>',
                  'naznacenie': 'Пищеварение'} if fields is None else fields
        with patch('api.views.discounted.positions_snapshot', return_value=positions), \
             patch('api.views.discounted.site_feed.pictures_for',
                   return_value=['https://horse-bio.ru/d/a.png', 'https://horse-bio.ru/d/b.png']), \
             patch('api.views.discounted.site_feed.description_for', return_value=description), \
             patch('api.views.discounted.site_feed.rich_fields_for', return_value=fields):
            return self.client.get('/api/discounted/export.csv')

    @staticmethod
    def _position(**kwargs):
        base = {'article': '01-01AP0500-UC', 'name': 'Уценка // Хондро', 'price': 1176.0,
                'price_full': 1680.0, 'quantity': 5, 'published': False, 'state': STATE_OK}
        base.update(kwargs)
        return base

    def test_returns_cp1251_file_for_positions_in_stock(self):
        response = self._get([self._position(), self._position(article='B-UC', quantity=0)])

        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        text = response.content.decode('cp1251')
        rows = text.splitlines()
        # шапка и одна позиция: карточки, которой нет ни на складе, ни на витрине,
        # в файле делать нечего
        self.assertEqual(len(rows), 2)
        self.assertIn('article : Артикул', rows[0])
        self.assertIn('01-01AP0500-UC', rows[1])
        # зачёркнутая цена — РРЦ, и обе картинки в одной колонке
        self.assertIn('1680.00', rows[1])
        # описание — врезка про срок плюс текст основной карточки
        self.assertIn('истекающим сроком годности', rows[1])
        self.assertIn('Текст основной карточки', rows[1])
        self.assertIn('https://horse-bio.ru/d/a.png, https://horse-bio.ru/d/b.png', rows[1])

    def test_does_not_hide_a_card_that_is_already_on_sale(self):
        """Импорт не должен снимать с витрины то, что уже продаётся."""
        live = self._get([self._position(published=True)]).content.decode('cp1251').splitlines()[1]
        new = self._get([self._position(published=False)]).content.decode('cp1251').splitlines()[1]
        columns = live.split(';')
        self.assertEqual(columns[3], '0')          # hidden
        self.assertEqual(new.split(';')[3], '1')

    def test_hides_a_card_that_must_be_taken_off_sale(self):
        """До конца срока меньше двух месяцев — файл снимает карточку с витрины.

        Это единственный оставшийся способ: обмен, который делал бы это сам,
        упёрся в демо-лимит.
        """
        for state in (STATE_DELIST, STATE_EXPIRED):
            with self.subTest(state=state):
                row = self._get([self._position(published=True, state=state)])
                columns = row.content.decode('cp1251').splitlines()[1].split(';')
                self.assertEqual(columns[3], '1')      # hidden

    def test_zeroes_and_hides_a_sold_out_card(self):
        """Раскупленная карточка обязана попасть в файл — иначе она останется в продаже."""
        response = self._get([self._position(quantity=0, published=True)])
        rows = response.content.decode('cp1251').splitlines()
        self.assertEqual(len(rows), 2)
        columns = rows[1].split(';')
        self.assertEqual(columns[3], '1')              # hidden
        self.assertEqual(columns[6], '0')              # amount

    def test_refuses_to_build_when_the_site_feed_is_unknown(self):
        """Не зная, что на витрине, файл снял бы с продажи весь раздел."""
        response = self._get([self._position(published=None), self._position(article='B-UC')])
        self.assertNotEqual(response.status_code, 200)
        self.assertIn('Фид сайта не ответил', response.json()['message'])

    def test_leaves_description_empty_when_the_source_page_is_unreadable(self):
        """Пустое описание лучше, чем затёртое: восстанавливать его неоткуда."""
        row = self._get([self._position()], description='').content.decode('cp1251').splitlines()[1]
        self.assertNotIn('истекающим сроком годности', row)

    def test_carries_the_extra_fields_of_the_source_card(self):
        """Состав, применение и назначение на сайте обязательные — без них не сохранить."""
        response = self._get([self._position()])
        rows = response.content.decode('cp1251').splitlines()

        self.assertIn('cf_sostav', rows[0])
        self.assertIn('cf_naznacenie', rows[0])
        # вёрстка сохраняется: в фиде значения приходят без тегов, поэтому
        # берём их со страницы товара
        self.assertIn('<h3>Состав</h3>', rows[1])

    def test_columns_follow_the_fields_that_actually_came(self):
        """Набор доп. полей задаётся в админке и у товаров разный."""
        header = self._get([self._position()], fields={'ves': '1600 г'}).content.decode('cp1251').splitlines()[0]
        self.assertIn('cf_ves', header)
        self.assertNotIn('cf_sostav', header)


class RefreshTest(TestCase):
    """«Обновить» должно перечитывать и витрину сайта, а не только МойСклад."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='sergey', password='secret')

    def tearDown(self):
        cache.clear()

    def test_refresh_rereads_the_feed(self):
        with patch('api.views.discounted._resolve_refs', return_value=(FOLDER_HREF, ATTR_ID)), \
             patch('api.views.discounted._get_all_pages', side_effect=[[], []]), \
             patch('api.views.discounted._build_analytics', return_value={}), \
             patch('api.views.discounted.ozon_stock.offers', return_value={}), \
             patch('api.views.discounted.site_feed.offers', return_value={}) as feed:
            self.client.get('/api/discounted/?refresh=1')

        self.assertTrue(feed.call_args.kwargs['refresh'])
