import json
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from ozon_logistics.models import (
    OzonAuthState, OzonDeliveryQuote, OzonOAuthToken, OzonPickupPoint, OzonProduct,
)
from ozon_logistics.services import catalog
from ozon_logistics import site_api
from ozon_logistics.services import orders
from ozon_logistics.services import pickup_points
from ozon_logistics.services import site_orders
from ozon_logistics.services import client as client_module
from ozon_logistics.services import oauth

CREDS = {
    'OZON_LOGISTICS_CLIENT_ID': 'test-client-id',
    'OZON_LOGISTICS_CLIENT_SECRET': 'test-client-secret',
    'OZON_LOGISTICS_REDIRECT_URI': 'http://example.test/api/ozon-logistics/oauth/callback',
}


def _jwt(**claims):
    """Собирает JWT-подобную строку: подпись нам не нужна, читается только payload."""
    import base64

    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
    return f'header.{body}.signature'


class FakeResponse:
    def __init__(self, status_code=200, data=None, text=''):
        self.status_code = status_code
        self._data = data
        self.text = text or json.dumps(data or {})

    def json(self):
        if self._data is None:
            raise ValueError('no json')
        return self._data


@patch.dict('os.environ', CREDS)
class AuthorizeUrlTests(TestCase):
    def test_contains_required_params(self):
        url, state = oauth.build_authorize_url()
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query['response_type'], ['code'])
        # Без offline Ozon не выдаст refresh_token — переавторизация станет ручной
        self.assertEqual(query['access_type'], ['offline'])
        self.assertEqual(query['client_id'], ['test-client-id'])
        self.assertEqual(query['redirect_uri'], [CREDS['OZON_LOGISTICS_REDIRECT_URI']])
        self.assertEqual(query['state'], [state])
        scopes = query['scope'][0].split(' ')
        self.assertIn('seller-api.ozon-logistics', scopes)
        # MIX-доставка возит и со складов Ozon — нужен доступ к FBO-отправлениям
        self.assertIn('seller-api.posting-fbo', scopes)

    def test_state_is_stored_and_single_use(self):
        _, state = oauth.build_authorize_url()
        self.assertTrue(OzonAuthState.objects.filter(state=state).exists())

        self.assertTrue(oauth.consume_state(state))
        self.assertFalse(oauth.consume_state(state))

    def test_expired_state_is_rejected(self):
        _, state = oauth.build_authorize_url()
        OzonAuthState.objects.filter(state=state).update(
            created_at=timezone.now() - OzonAuthState.LIFETIME - timezone.timedelta(minutes=1)
        )
        self.assertFalse(oauth.consume_state(state))


@patch.dict('os.environ', CREDS)
class ExchangeCodeTests(TestCase):
    def test_stores_token_with_expiry(self):
        payload = {
            'access_token': 'access-1',
            'refresh_token': 'refresh-1',
            'expires_in': 3600,
            'scope': 'seller-api.ozon-logistics',
        }
        with patch('requests.post', return_value=FakeResponse(data=payload)) as post:
            token = oauth.exchange_code('code-1')

        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['grant_type'], 'authorization_code')
        self.assertEqual(sent['code'], 'code-1')
        self.assertEqual(sent['redirect_uri'], CREDS['OZON_LOGISTICS_REDIRECT_URI'])

        self.assertEqual(token.access_token, 'access-1')
        self.assertFalse(token.is_expired())
        self.assertEqual(OzonOAuthToken.objects.count(), 1)

    def test_second_exchange_reuses_single_row(self):
        payload = {'access_token': 'a', 'refresh_token': 'r', 'expires_in': 60}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            oauth.exchange_code('code-1')
            oauth.exchange_code('code-2')
        self.assertEqual(OzonOAuthToken.objects.count(), 1)

    def test_error_body_is_surfaced(self):
        response = FakeResponse(status_code=400, data=None, text='{"message":"bad code"}')
        with patch('requests.post', return_value=response):
            with self.assertRaises(oauth.OzonOAuthError) as ctx:
                oauth.exchange_code('code-1')
        self.assertIn('bad code', str(ctx.exception))

    def test_expiry_comes_from_jwt(self):
        exp = int((timezone.now() + timezone.timedelta(hours=2)).timestamp())
        with patch('requests.post', return_value=FakeResponse(data={'access_token': _jwt(exp=exp)})):
            token = oauth.exchange_code('code-1')

        self.assertAlmostEqual(int(token.expires_at.timestamp()), exp, delta=2)

    def test_jwt_wins_over_expires_in(self):
        """exp выдал сам Ozon и по нему же проверяет токен — он авторитетнее."""
        exp = int((timezone.now() + timezone.timedelta(hours=2)).timestamp())
        payload = {'access_token': _jwt(exp=exp), 'expires_in': 60}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            token = oauth.exchange_code('code-1')

        self.assertAlmostEqual(int(token.expires_at.timestamp()), exp, delta=2)

    def test_implausible_expires_in_is_ignored(self):
        """Ozon прислал ~1.79e9 — это 57 лет; такое значение не длительность."""
        payload = {'access_token': 'not-a-jwt', 'expires_in': 1787702399}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            token = oauth.exchange_code('code-1')

        horizon = timezone.now() + oauth.MAX_PLAUSIBLE_LIFETIME
        self.assertLess(token.expires_at, horizon)

    def test_plausible_expires_in_is_used_without_jwt(self):
        payload = {'access_token': 'not-a-jwt', 'expires_in': 3600}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            token = oauth.exchange_code('code-1')

        expected = timezone.now() + timezone.timedelta(seconds=3600)
        self.assertAlmostEqual(token.expires_at.timestamp(), expected.timestamp(), delta=5)


@patch.dict('os.environ', CREDS)
class GetValidTokenTests(TestCase):
    def _token(self, *, expires_in_seconds, refresh='refresh-1'):
        return OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='old-access',
            refresh_token=refresh,
            expires_at=timezone.now() + timezone.timedelta(seconds=expires_in_seconds),
        )

    def test_returns_existing_token_when_fresh(self):
        self._token(expires_in_seconds=3600)
        with patch('requests.post') as post:
            self.assertEqual(oauth.get_valid_token(), 'old-access')
        post.assert_not_called()

    def test_refreshes_expired_token(self):
        self._token(expires_in_seconds=-10)
        payload = {'access_token': 'new-access', 'refresh_token': 'refresh-2', 'expires_in': 3600}
        with patch('requests.post', return_value=FakeResponse(data=payload)) as post:
            self.assertEqual(oauth.get_valid_token(), 'new-access')
        self.assertEqual(post.call_args.kwargs['json']['grant_type'], 'refresh_token')

    def test_keeps_previous_refresh_token_when_ozon_omits_it(self):
        self._token(expires_in_seconds=-10)
        with patch('requests.post', return_value=FakeResponse(data={'access_token': 'new', 'expires_in': 60})):
            oauth.get_valid_token()
        self.assertEqual(OzonOAuthToken.objects.get().refresh_token, 'refresh-1')

    def test_without_token_asks_to_authorize(self):
        with self.assertRaises(oauth.OzonOAuthError) as ctx:
            oauth.get_valid_token()
        self.assertIn('oauth/start', str(ctx.exception))

    def test_expired_without_refresh_token_asks_to_reauthorize(self):
        self._token(expires_in_seconds=-10, refresh='')
        with self.assertRaises(oauth.OzonOAuthError) as ctx:
            oauth.get_valid_token()
        self.assertIn('повторная авторизация', str(ctx.exception))


class NormalizePhoneTests(TestCase):
    def test_strips_formatting(self):
        self.assertEqual(client_module.normalize_phone('+7 (916) 622-90-30'), '79166229030')

    def test_leading_eight_becomes_country_code(self):
        self.assertEqual(client_module.normalize_phone('89166229030'), '79166229030')

    def test_adds_country_code_to_ten_digits(self):
        self.assertEqual(client_module.normalize_phone('9166229030'), '79166229030')

    def test_already_normalized_is_unchanged(self):
        self.assertEqual(client_module.normalize_phone('79166229030'), '79166229030')

    def test_too_short_is_rejected(self):
        with self.assertRaises(client_module.OzonLogisticsError):
            client_module.normalize_phone('12345')


@patch.dict('os.environ', CREDS)
class ClientTests(TestCase):
    def setUp(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='refresh-1',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

    def test_sends_bearer_token(self):
        with patch('requests.post', return_value=FakeResponse(data={'result': []})) as post:
            client_module.OzonLogisticsClient().delivery_check('+79161112233')
        headers = post.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer access-1')

    def test_phone_is_normalized_before_sending(self):
        """Ozon принимает только цифры: ^\\d{10,15}$."""
        with patch('requests.post', return_value=FakeResponse(data={'result': []})) as post:
            client_module.OzonLogisticsClient().delivery_check('+7 (916) 622-90-30')
        self.assertEqual(post.call_args.kwargs['json'], {'client_phone': '79166229030'})

    def test_retries_once_after_401(self):
        refreshed = FakeResponse(data={'access_token': 'access-2', 'expires_in': 3600})
        responses = [
            FakeResponse(status_code=401, text='unauthorized'),  # Seller API
            refreshed,                                            # обновление токена
            FakeResponse(data={'result': ['ok']}),                # повтор
        ]
        with patch('requests.post', side_effect=responses):
            result = client_module.OzonLogisticsClient().delivery_check('+79161112233')
        self.assertEqual(result, {'result': ['ok']})

    def test_raises_with_response_body(self):
        with patch('requests.post', return_value=FakeResponse(status_code=403, text='forbidden')):
            with self.assertRaises(client_module.OzonLogisticsError) as ctx:
                client_module.OzonLogisticsClient().delivery_check('+79161112233')
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn('forbidden', str(ctx.exception))


@patch.dict('os.environ', CREDS)
class CallbackViewTests(TestCase):
    def test_unknown_state_is_rejected(self):
        response = self.client.get(
            '/api/ozon-logistics/oauth/callback', {'code': 'c', 'state': 'unknown'}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(OzonOAuthToken.objects.count(), 0)

    def test_valid_callback_stores_token(self):
        _, state = oauth.build_authorize_url()
        payload = {'access_token': 'a', 'refresh_token': 'r', 'expires_in': 3600}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            response = self.client.get(
                '/api/ozon-logistics/oauth/callback', {'code': 'c', 'state': state}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(OzonOAuthToken.objects.get().access_token, 'a')

    def test_callback_is_public(self):
        """Без сессии Инсайта — Ozon возвращает продавца в его собственном браузере."""
        response = self.client.get('/api/ozon-logistics/oauth/callback')
        self.assertNotEqual(response.status_code, 401)

    def test_ozon_error_is_reported(self):
        response = self.client.get(
            '/api/ozon-logistics/oauth/callback',
            {'error': 'access_denied', 'error_description': 'seller refused'},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('access_denied', response.content.decode())

    def test_error_params_are_escaped(self):
        """Публичный путь: параметры Ozon не должны попадать в HTML как разметка."""
        response = self.client.get(
            '/api/ozon-logistics/oauth/callback',
            {'error': '<img src=x onerror=alert(1)>', 'error_description': 'bad'},
        )
        body = response.content.decode()
        self.assertNotIn('<img src=x', body)
        self.assertIn('&lt;img src=x', body)

    def test_success_page_shows_local_time(self):
        _, state = oauth.build_authorize_url()
        payload = {'access_token': 'a', 'refresh_token': 'r', 'expires_in': 3600}
        with patch('requests.post', return_value=FakeResponse(data=payload)):
            response = self.client.get(
                '/api/ozon-logistics/oauth/callback', {'code': 'c', 'state': state}
            )
        expected = timezone.localtime(
            OzonOAuthToken.objects.get().expires_at
        ).strftime('%d.%m.%Y %H:%M')
        self.assertIn(expected, response.content.decode())

    def test_reauthorization_keeps_refresh_token_when_omitted(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='old',
            refresh_token='refresh-1',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        _, state = oauth.build_authorize_url()
        with patch('requests.post', return_value=FakeResponse(data={'access_token': 'new', 'expires_in': 60})):
            self.client.get('/api/ozon-logistics/oauth/callback', {'code': 'c', 'state': state})
        self.assertEqual(OzonOAuthToken.objects.get().refresh_token, 'refresh-1')


@patch.dict('os.environ', CREDS)
class AccessControlTests(TestCase):
    """Токен один на всю систему: запускать авторизацию может только админ."""

    def _user(self, *, superuser):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        if superuser:
            return User.objects.create_superuser('admin-u', 'a@test.local', 'pwd12345')
        return User.objects.create_user('plain-u', 'p@test.local', 'pwd12345')

    def test_start_is_forbidden_for_regular_user(self):
        self.client.force_login(self._user(superuser=False))
        response = self.client.get('/api/ozon-logistics/oauth/start/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(OzonAuthState.objects.count(), 0)

    def test_status_is_forbidden_for_regular_user(self):
        self.client.force_login(self._user(superuser=False))
        response = self.client.get('/api/ozon-logistics/oauth/status/')
        self.assertEqual(response.status_code, 403)

    def test_start_redirects_superuser_to_ozon(self):
        self.client.force_login(self._user(superuser=True))
        response = self.client.get('/api/ozon-logistics/oauth/start/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith(oauth.AUTHORIZE_URL))

    def test_status_without_token(self):
        self.client.force_login(self._user(superuser=True))
        response = self.client.get('/api/ozon-logistics/oauth/status/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['authorized'])

    def test_status_exposes_token_claims(self):
        exp = int((timezone.now() + timezone.timedelta(hours=2)).timestamp())
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token=_jwt(exp=exp, iat=exp - 7200),
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=2),
        )
        self.client.force_login(self._user(superuser=True))
        claims = self.client.get('/api/ozon-logistics/oauth/status/').json()['token_claims']
        self.assertEqual(claims['exp'], exp)
        self.assertIsNotNone(claims['exp_readable'])

    def test_diag_is_forbidden_for_regular_user(self):
        self.client.force_login(self._user(superuser=False))
        self.assertEqual(self.client.get('/api/ozon-logistics/diag/').status_code, 403)

    def test_diag_requires_phone(self):
        self.client.force_login(self._user(superuser=True))
        self.assertEqual(self.client.get('/api/ozon-logistics/diag/').status_code, 400)

    def test_diag_calls_seller_api(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.client.force_login(self._user(superuser=True))
        with patch('requests.post', return_value=FakeResponse(data={'result': ['w1']})):
            response = self.client.get('/api/ozon-logistics/diag/', {'phone': '+79161112233'})
        self.assertEqual(response.json()['result'], {'result': ['w1']})

    def test_point_info_rejects_empty_and_oversized_lists(self):
        with self.assertRaises(client_module.OzonLogisticsError):
            client_module.OzonLogisticsClient().point_info([])
        with self.assertRaises(client_module.OzonLogisticsError):
            client_module.OzonLogisticsClient().point_info(list(range(101)))

    def test_diag_points_returns_count_and_sample(self):
        """Полный список ПВЗ огромный — наружу отдаём счётчик и образец."""
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        points = [{'map_point_id': i, 'coordinate': {'lat': 55.7, 'long': 37.6}} for i in range(12)]
        self.client.force_login(self._user(superuser=True))
        with patch('requests.post', return_value=FakeResponse(data={'points': points})):
            body = self.client.get('/api/ozon-logistics/diag/points/').json()
        self.assertEqual(body['result']['points_total'], 12)
        self.assertEqual(len(body['result']['sample']), 5)

    def test_diag_point_info_requires_ids(self):
        self.client.force_login(self._user(superuser=True))
        self.assertEqual(self.client.get('/api/ozon-logistics/diag/point/').status_code, 400)

    def test_diag_point_info_passes_ids(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.client.force_login(self._user(superuser=True))
        with patch('requests.post', return_value=FakeResponse(data={'points': []})) as post:
            self.client.get('/api/ozon-logistics/diag/point/', {'ids': '12, 34'})
        self.assertEqual(post.call_args.kwargs['json'], {'map_point_ids': ['12', '34']})

    def test_checkout_requires_exactly_one_destination(self):
        client = client_module.OzonLogisticsClient()
        items = [{'offer_id': 'A', 'sku': 1, 'quantity': 1}]
        with self.assertRaises(client_module.OzonLogisticsError):
            client.checkout(phone='79161112233', items=items)
        with self.assertRaises(client_module.OzonLogisticsError):
            client.checkout(phone='79161112233', items=items, map_point_id=1, coordinates=(55.7, 37.6))

    def test_checkout_rejects_empty_items(self):
        with self.assertRaises(client_module.OzonLogisticsError):
            client_module.OzonLogisticsClient().checkout(
                phone='79161112233', items=[], map_point_id=1
            )

    def test_checkout_builds_pickup_payload(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        with patch('requests.post', return_value=FakeResponse(data={'splits': []})) as post:
            client_module.OzonLogisticsClient().checkout(
                phone='+7 (916) 111-22-33',
                items=[{'offer_id': 'ART-1', 'sku': '42', 'quantity': '2'}],
                map_point_id='7',
            )
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['buyer_phone'], '79161112233')
        self.assertEqual(sent['delivery_schema'], 'MIX')
        self.assertEqual(sent['delivery_type'], {'pick_up': {'map_point_id': 7}})
        # Ozon отвергает позицию с обоими идентификаторами сразу
        self.assertEqual(sent['items'], [{'sku': 42, 'quantity': 2}])

    def test_checkout_falls_back_to_offer_id(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        with patch('requests.post', return_value=FakeResponse(data={'splits': []})) as post:
            client_module.OzonLogisticsClient().checkout(
                phone='79161112233',
                items=[{'offer_id': 'ART-1', 'quantity': 1}],
                map_point_id=7,
            )
        self.assertEqual(post.call_args.kwargs['json']['items'], [{'offer_id': 'ART-1', 'quantity': 1}])

    def test_checkout_item_without_identifiers_is_rejected(self):
        with self.assertRaises(client_module.OzonLogisticsError):
            client_module.OzonLogisticsClient().checkout(
                phone='79161112233', items=[{'quantity': 1}], map_point_id=7
            )

    def test_checkout_builds_courier_payload(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        with patch('requests.post', return_value=FakeResponse(data={'splits': []})) as post:
            client_module.OzonLogisticsClient().checkout(
                phone='79161112233',
                items=[{'offer_id': 'ART-1', 'sku': 42, 'quantity': 1}],
                coordinates=(55.75, 37.61),
            )
        self.assertEqual(
            post.call_args.kwargs['json']['delivery_type'],
            {'courier': {'coordinates': {'latitude': 55.75, 'longitude': 37.61}}},
        )

    def test_warehouse_list_sends_required_limit(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        with patch('requests.post', return_value=FakeResponse(data={'warehouses': []})) as post:
            client_module.OzonLogisticsClient().warehouse_list()
        self.assertEqual(post.call_args.kwargs['json'], {'limit': 200})

    def test_product_list_filters_by_offer_id(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        with patch('requests.post', return_value=FakeResponse(data={'result': {}})) as post:
            client_module.OzonLogisticsClient().product_list(offer_ids=['A1', 'A2'])
        self.assertEqual(post.call_args.kwargs['json']['filter'], {'offer_id': ['A1', 'A2']})

    def test_diag_checkout_requires_params(self):
        self.client.force_login(self._user(superuser=True))
        response = self.client.get('/api/ozon-logistics/diag/checkout/', {'phone': '79161112233'})
        self.assertEqual(response.status_code, 400)

    def test_diag_checkout_rejects_bad_coords(self):
        self.client.force_login(self._user(superuser=True))
        response = self.client.get('/api/ozon-logistics/diag/checkout/', {
            'phone': '79161112233', 'offer_id': 'A', 'sku': '1', 'coords': 'москва',
        })
        self.assertEqual(response.status_code, 400)

    def test_diag_points_is_forbidden_for_regular_user(self):
        self.client.force_login(self._user(superuser=False))
        self.assertEqual(self.client.get('/api/ozon-logistics/diag/points/').status_code, 403)

    def test_diag_reports_seller_api_failure(self):
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )
        self.client.force_login(self._user(superuser=True))
        with patch('requests.post', return_value=FakeResponse(status_code=403, text='no scope')):
            response = self.client.get('/api/ozon-logistics/diag/', {'phone': '+79161112233'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('no scope', response.json()['message'])


class FakeCatalogClient:
    """Клиент-заглушка: отдаёт страницы каталога по порядку."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def product_list(self, *, limit=None, last_id=None, offer_ids=None):
        self.calls.append({'limit': limit, 'last_id': last_id})
        page = self.pages[len(self.calls) - 1]
        return {'result': page}


class CatalogSyncTests(TestCase):
    def test_stores_offer_id_to_sku_mapping(self):
        client = FakeCatalogClient([{
            'items': [
                {'offer_id': 'ART-1', 'sku': 111, 'product_id': 1, 'has_fbs_stocks': True},
                {'offer_id': 'ART-2', 'sku': 222, 'product_id': 2, 'archived': True},
                {'offer_id': 'ART-3', 'sku': 333, 'has_fbo_stocks': True},
                {'offer_id': 'ART-4', 'sku': 444},
            ],
            'last_id': None,
        }])
        stats = catalog.sync_products(client=client)

        self.assertEqual(stats['fetched'], 4)
        self.assertEqual(stats['created'], 4)
        self.assertEqual(OzonProduct.objects.get(offer_id='ART-1').sku, 111)
        # Годны товары с остатком где угодно (MIX), но не архивные и не пустые
        self.assertEqual(stats['sellable'], 2)

    def test_second_run_updates_instead_of_duplicating(self):
        page = {'items': [{'offer_id': 'ART-1', 'sku': 111, 'has_fbs_stocks': False}], 'last_id': None}
        catalog.sync_products(client=FakeCatalogClient([page]))

        changed = {'items': [{'offer_id': 'ART-1', 'sku': 111, 'has_fbs_stocks': True}], 'last_id': None}
        stats = catalog.sync_products(client=FakeCatalogClient([changed]))

        self.assertEqual(stats['updated'], 1)
        self.assertEqual(OzonProduct.objects.count(), 1)
        self.assertTrue(OzonProduct.objects.get().has_fbs_stocks)

    def test_item_without_sku_is_skipped(self):
        """Товар без sku для Ozon Доставки бесполезен — заказ по нему не создать."""
        client = FakeCatalogClient([{
            'items': [
                {'offer_id': 'ART-1', 'sku': None},
                {'offer_id': '', 'sku': 333},
            ],
            'last_id': None,
        }])
        stats = catalog.sync_products(client=client)

        self.assertEqual(stats['skipped_without_sku'], 2)
        self.assertEqual(OzonProduct.objects.count(), 0)

    def test_pagination_follows_last_id(self):
        full_page = {
            'items': [
                {'offer_id': f'ART-{i}', 'sku': 1000 + i, 'has_fbs_stocks': True}
                for i in range(catalog.PAGE_SIZE)
            ],
            'last_id': 'cursor-1',
        }
        tail = {'items': [{'offer_id': 'ART-LAST', 'sku': 9999}], 'last_id': None}
        client = FakeCatalogClient([full_page, tail])

        stats = catalog.sync_products(client=client)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[1]['last_id'], 'cursor-1')
        self.assertEqual(stats['fetched'], catalog.PAGE_SIZE + 1)

    def test_empty_catalog_is_not_an_error(self):
        stats = catalog.sync_products(client=FakeCatalogClient([{'items': [], 'last_id': None}]))
        self.assertEqual(stats['fetched'], 0)
        self.assertEqual(stats['total_stored'], 0)

    def test_sellable_property(self):
        product = OzonProduct(offer_id='A', sku=1, has_fbs_stocks=True, archived=False)
        self.assertTrue(product.sellable_via_ozon_delivery)

        # Остаток только на складе Ozon — при MIX тоже годится
        product.has_fbs_stocks = False
        product.has_fbo_stocks = True
        self.assertTrue(product.sellable_via_ozon_delivery)

        product.archived = True
        self.assertFalse(product.sellable_via_ozon_delivery)

        product.archived = False
        product.has_fbo_stocks = False
        self.assertFalse(product.sellable_via_ozon_delivery)


class FakePointsClient:
    def __init__(self, points=None, info=None):
        self._points = points or []
        self._info = info or {'points': []}
        self.info_calls = []

    def point_list(self):
        return {'points': self._points}

    def point_info(self, ids):
        self.info_calls.append(list(ids))
        return self._info


def _point(point_id, lat=55.7, long=37.6):
    return {'map_point_id': point_id, 'coordinate': {'lat': lat, 'long': long}}


class PickupPointSyncTests(TestCase):
    def test_stores_coordinates(self):
        client = FakePointsClient([_point(1), _point(2, 60.0, 30.3)])
        stats = pickup_points.sync_pickup_points(client=client)

        self.assertEqual(stats['fetched'], 2)
        self.assertEqual(stats['created'], 2)
        self.assertEqual(OzonPickupPoint.objects.get(pk=2).latitude, 60.0)

    def test_second_run_updates_without_duplicating(self):
        pickup_points.sync_pickup_points(client=FakePointsClient([_point(1)]))
        stats = pickup_points.sync_pickup_points(client=FakePointsClient([_point(1, 10.0, 20.0)]))

        self.assertEqual(stats['updated'], 1)
        self.assertEqual(OzonPickupPoint.objects.count(), 1)
        self.assertEqual(OzonPickupPoint.objects.get().latitude, 10.0)

    def test_point_without_coordinates_is_skipped(self):
        client = FakePointsClient([{'map_point_id': 5}, {'coordinate': {'lat': 1, 'long': 2}}])
        stats = pickup_points.sync_pickup_points(client=client)

        self.assertEqual(stats['skipped'], 2)
        self.assertEqual(OzonPickupPoint.objects.count(), 0)

    def test_empty_response_keeps_existing_points(self):
        """Пустой ответ — повод не трогать таблицу, а не стереть все ПВЗ."""
        pickup_points.sync_pickup_points(client=FakePointsClient([_point(1)]))
        stats = pickup_points.sync_pickup_points(client=FakePointsClient([]))

        self.assertEqual(stats['total_stored'], 1)
        self.assertEqual(OzonPickupPoint.objects.count(), 1)


class PickupPointBoundsTests(TestCase):
    def setUp(self):
        OzonPickupPoint.objects.bulk_create([
            OzonPickupPoint(map_point_id=1, latitude=55.75, longitude=37.61),   # Москва
            OzonPickupPoint(map_point_id=2, latitude=59.93, longitude=30.33),   # Петербург
            OzonPickupPoint(map_point_id=3, latitude=55.80, longitude=37.50),   # Москва
        ])

    def test_returns_only_points_inside_viewport(self):
        found = OzonPickupPoint.in_bounds(south=55.5, west=37.3, north=56.0, east=37.9)
        self.assertEqual({p.map_point_id for p in found}, {1, 3})

    def test_limit_caps_result(self):
        found = OzonPickupPoint.in_bounds(south=0, west=0, north=90, east=90, limit=1)
        self.assertEqual(len(list(found)), 1)


class PickupPointDetailsTests(TestCase):
    def setUp(self):
        OzonPickupPoint.objects.create(map_point_id=7, latitude=55.7, longitude=37.6)

    def test_fetches_and_stores_details(self):
        client = FakePointsClient(info={'points': [{
            'delivery_method': {
                'map_point_id': 7,
                'name': 'Пункт Ozon',
                'address': 'Москва, Тверская, 1',
            },
            'enabled': True,
        }]})

        result = pickup_points.fetch_details([7], client=client)

        point = OzonPickupPoint.objects.get(pk=7)
        self.assertEqual(point.address, 'Москва, Тверская, 1')
        self.assertIsNotNone(point.details_synced_at)
        self.assertEqual(len(result), 1)

    def test_known_details_are_not_refetched(self):
        """Подробности берём у Ozon один раз — дальше отдаём из базы."""
        client = FakePointsClient(info={'points': [{
            'delivery_method': {'map_point_id': 7, 'address': 'Адрес'},
        }]})
        pickup_points.fetch_details([7], client=client)
        pickup_points.fetch_details([7], client=client)

        self.assertEqual(len(client.info_calls), 1)

    def test_request_is_capped_at_hundred(self):
        OzonPickupPoint.objects.bulk_create([
            OzonPickupPoint(map_point_id=i, latitude=1.0, longitude=1.0)
            for i in range(100, 250)
        ])
        client = FakePointsClient(info={'points': []})
        pickup_points.fetch_details(range(100, 250), client=client)

        self.assertEqual(len(client.info_calls[0]), 100)

    def test_empty_input_makes_no_request(self):
        client = FakePointsClient()
        self.assertEqual(pickup_points.fetch_details([], client=client), [])
        self.assertEqual(client.info_calls, [])


def _checkout_response(*, available=True, sku=758646053, warehouse_id=23996939891000):
    """Ответ checkout по образцу живого — с ним и сверялись поля."""
    return {'splits': [{
        'delivery_method': {
            'id': 378617,
            'name': 'Пункт Ozon',
            'delivery_type': 'PVZ',
            'timeslots': [{
                'timeslot_id': 1014000655935686,
                'logistic_date_range': {
                    'from': '2026-09-04T17:00:00Z', 'to': '2026-09-04T18:00:00Z',
                },
                'client_date_range': None,
            }],
            'unavailable_reason': 'UNSPECIFIED',
        },
        'warehouse_id': warehouse_id,
        'items': [{'sku': sku, 'quantity': 1, 'offer_id': '01-14AP0250'}],
        'unavailable_reason': 'UNSPECIFIED' if available else 'OUT_OF_STOCK',
        'delivery_schema': 'FBS',
        'commissions': {'total': {'amount': '100', 'currency': 'RUB'}} if available else None,
    }]}


class FakeOrderClient:
    def __init__(self, checkout=None, order=None, order_error=None):
        self._checkout = checkout or _checkout_response()
        self._order = order or {'order_number': 'OZ-1'}
        self._order_error = order_error
        self.order_payloads = []

    def checkout(self, **kwargs):
        self.checkout_kwargs = kwargs
        return self._checkout

    def order_create(self, payload):
        self.order_payloads.append(payload)
        if self._order_error:
            raise client_module.OzonLogisticsError(self._order_error)
        return self._order


BUYER = {'first_name': 'Иван', 'last_name': 'Петров', 'phone': '+7 (916) 111-22-33'}


class QuoteTests(TestCase):
    def test_saves_quote_with_delivery_cost(self):
        client = FakeOrderClient()
        quote = orders.create_quote(
            phone='79161112233',
            items=[{'sku': 758646053, 'quantity': 1}],
            map_point_id=378617,
            client=client,
        )

        self.assertEqual(quote.delivery_cost, Decimal('100'))
        self.assertTrue(quote.is_deliverable)
        self.assertEqual(quote.phone, '79161112233')

    def test_unavailable_delivery_is_recognised(self):
        client = FakeOrderClient(checkout=_checkout_response(available=False))
        quote = orders.create_quote(
            phone='79161112233', items=[{'sku': 1, 'quantity': 1}],
            map_point_id=1, client=client,
        )

        self.assertFalse(quote.is_deliverable)
        self.assertEqual(quote.unavailable_reasons(), ['OUT_OF_STOCK'])


class OrderPayloadTests(TestCase):
    def _quote(self, **kwargs):
        defaults = {
            'phone': '79161112233',
            'items': [{'sku': 758646053, 'quantity': 1}],
            'map_point_id': 378617,
            'checkout_response': _checkout_response(),
        }
        return OzonDeliveryQuote.objects.create(**{**defaults, **kwargs})

    def test_builds_required_fields(self):
        payload = orders.build_order_payload(
            self._quote(), buyer=BUYER, prices={758646053: Decimal('1990.50')}
        )

        split = payload['splits'][0]
        method = split['delivery_method']
        self.assertEqual(method['delivery_method_id'], 378617)
        self.assertEqual(method['delivery_type'], 'PVZ')
        self.assertEqual(method['timeslot_id'], 1014000655935686)
        self.assertIn('from', method['logistic_date_range'])
        self.assertEqual(split['warehouse_id'], 23996939891000)
        self.assertEqual(payload['delivery'], {'pick_up': {'map_point_id': 378617}})
        self.assertEqual(payload['delivery_schema'], 'MIX')

    def test_price_is_split_into_units_and_nanos(self):
        payload = orders.build_order_payload(
            self._quote(), buyer=BUYER, prices={758646053: Decimal('1990.50')}
        )
        price = payload['splits'][0]['items'][0]['price']
        self.assertEqual(price, {'currency_code': 'RUB', 'units': 1990, 'nanos': 500000000})

    def test_phone_is_normalized_for_buyer_and_recipient(self):
        payload = orders.build_order_payload(
            self._quote(), buyer=BUYER, prices={758646053: Decimal('100')}
        )
        self.assertEqual(payload['buyer']['phone'], '79161112233')
        self.assertEqual(payload['recipient']['recipient_phone'], '79161112233')

    def test_missing_price_is_rejected(self):
        with self.assertRaises(orders.OzonOrderError):
            orders.build_order_payload(self._quote(), buyer=BUYER, prices={})

    def test_unavailable_quote_is_rejected(self):
        quote = self._quote(checkout_response=_checkout_response(available=False))
        with self.assertRaises(orders.OzonOrderError) as ctx:
            orders.build_order_payload(quote, buyer=BUYER, prices={758646053: Decimal('1')})
        self.assertIn('OUT_OF_STOCK', str(ctx.exception))

    def test_quote_without_destination_is_rejected(self):
        quote = self._quote(map_point_id=None)
        with self.assertRaises(orders.OzonOrderError):
            orders.build_order_payload(quote, buyer=BUYER, prices={758646053: Decimal('1')})

    def test_courier_address_is_used_when_no_pickup_point(self):
        quote = self._quote(
            map_point_id=None,
            courier_address={'city': 'Москва', 'country': 'Россия', 'house_number': '1'},
        )
        payload = orders.build_order_payload(
            quote, buyer=BUYER, prices={758646053: Decimal('1')}
        )
        self.assertEqual(payload['delivery']['courier']['city'], 'Москва')


class CreateOrderTests(TestCase):
    def _quote(self):
        return OzonDeliveryQuote.objects.create(
            phone='79161112233',
            items=[{'sku': 758646053, 'quantity': 1}],
            map_point_id=378617,
            checkout_response=_checkout_response(),
        )

    def test_stores_order_number(self):
        quote = self._quote()
        client = FakeOrderClient()

        orders.create_order(quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=client)

        quote.refresh_from_db()
        self.assertEqual(quote.status, OzonDeliveryQuote.STATUS_ORDERED)
        self.assertEqual(quote.order_number, 'OZ-1')
        self.assertIsNotNone(quote.ordered_at)

    def test_second_call_does_not_create_duplicate(self):
        """Дубль означал бы вторую отгрузку тому же покупателю."""
        quote = self._quote()
        client = FakeOrderClient()
        orders.create_order(quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=client)
        orders.create_order(quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=client)

        self.assertEqual(len(client.order_payloads), 1)

    def test_failure_is_recorded_on_quote(self):
        quote = self._quote()
        client = FakeOrderClient(order_error='HTTP 400: out of stock')

        with self.assertRaises(orders.OzonOrderError):
            orders.create_order(quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=client)

        quote.refresh_from_db()
        self.assertEqual(quote.status, OzonDeliveryQuote.STATUS_FAILED)
        self.assertIn('out of stock', quote.error)


@patch.dict('os.environ', CREDS)
class SiteApiTests(TestCase):
    """Публичные эндпоинты корзины: без сессии, но с пределом частоты."""

    def setUp(self):
        cache.clear()
        OzonOAuthToken.objects.create(
            pk=OzonOAuthToken.SINGLETON_PK,
            access_token='access-1',
            refresh_token='r',
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

    def tearDown(self):
        cache.clear()

    def test_availability_works_without_login(self):
        with patch('requests.post', return_value=FakeResponse(data={'is_possible': True})):
            response = self.client.post(
                '/api/ozon-logistics/site/availability/',
                data=json.dumps({'phone': '+7 (916) 111-22-33'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['available'])

    def test_availability_requires_phone(self):
        response = self.client.post(
            '/api/ozon-logistics/site/availability/',
            data=json.dumps({}), content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_upstream_error_is_not_leaked(self):
        """Наружу не должны утекать подробности ответа Ozon."""
        with patch('requests.post', return_value=FakeResponse(status_code=403, text='secret detail')):
            response = self.client.post(
                '/api/ozon-logistics/site/availability/',
                data=json.dumps({'phone': '79161112233'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret detail', response.content.decode())

    def test_rate_limit_kicks_in(self):
        with patch('requests.post', return_value=FakeResponse(data={'is_possible': True})):
            for _ in range(site_api.RATE_LIMITS['availability']):
                self.client.post(
                    '/api/ozon-logistics/site/availability/',
                    data=json.dumps({'phone': '79161112233'}),
                    content_type='application/json',
                )
            response = self.client.post(
                '/api/ozon-logistics/site/availability/',
                data=json.dumps({'phone': '79161112233'}),
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 429)

    def test_points_come_from_local_cache(self):
        OzonPickupPoint.objects.create(map_point_id=1, latitude=55.75, longitude=37.61)
        OzonPickupPoint.objects.create(map_point_id=2, latitude=59.93, longitude=30.33)

        with patch('requests.post') as post:
            response = self.client.get('/api/ozon-logistics/site/points/', {
                'south': 55.5, 'west': 37.3, 'north': 56.0, 'east': 37.9,
            })

        post.assert_not_called()  # к Ozon не ходим
        self.assertEqual([p['id'] for p in response.json()['points']], [1])

    def test_points_validate_bounds(self):
        response = self.client.get('/api/ozon-logistics/site/points/', {'south': 1})
        self.assertEqual(response.status_code, 400)

        response = self.client.get('/api/ozon-logistics/site/points/', {
            'south': 60, 'west': 37, 'north': 55, 'east': 38,
        })
        self.assertEqual(response.status_code, 400)

    def test_quote_translates_offer_id_to_sku(self):
        OzonProduct.objects.create(offer_id='01-14AP0250', sku=758646053, has_fbs_stocks=True)
        client = FakeOrderClient()

        with patch('ozon_logistics.services.orders.OzonLogisticsClient', return_value=client):
            response = self.client.post(
                '/api/ozon-logistics/site/quote/',
                data=json.dumps({
                    'phone': '79161112233',
                    'items': [{'offer_id': '01-14AP0250', 'quantity': 2}],
                    'map_point_id': 378617,
                }),
                content_type='application/json',
            )

        body = response.json()
        self.assertTrue(body['available'])
        self.assertEqual(body['delivery_cost'], 100.0)
        self.assertEqual(client.checkout_kwargs['items'], [{'sku': 758646053, 'quantity': 2}])
        self.assertTrue(OzonDeliveryQuote.objects.filter(pk=body['quote_id']).exists())

    def test_quote_reports_unknown_product(self):
        response = self.client.post(
            '/api/ozon-logistics/site/quote/',
            data=json.dumps({
                'phone': '79161112233',
                'items': [{'offer_id': 'НЕТ-ТАКОГО', 'quantity': 1}],
                'map_point_id': 1,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('НЕТ-ТАКОГО', response.json()['message'])

    def test_quote_requires_destination(self):
        OzonProduct.objects.create(offer_id='A', sku=1, has_fbs_stocks=True)
        response = self.client.post(
            '/api/ozon-logistics/site/quote/',
            data=json.dumps({'phone': '79161112233', 'items': [{'offer_id': 'A', 'quantity': 1}]}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_quote_reports_unavailable_delivery(self):
        OzonProduct.objects.create(offer_id='A', sku=1, has_fbs_stocks=True)
        client = FakeOrderClient(checkout=_checkout_response(available=False, sku=1))

        with patch('ozon_logistics.services.orders.OzonLogisticsClient', return_value=client):
            response = self.client.post(
                '/api/ozon-logistics/site/quote/',
                data=json.dumps({
                    'phone': '79161112233',
                    'items': [{'offer_id': 'A', 'quantity': 1}],
                    'map_point_id': 1,
                }),
                content_type='application/json',
            )

        body = response.json()
        self.assertFalse(body['available'])
        self.assertEqual(body['reasons'], ['OUT_OF_STOCK'])

    def test_point_details_are_fetched_once(self):
        OzonPickupPoint.objects.create(map_point_id=7, latitude=55.7, longitude=37.6)
        info = {'points': [{'delivery_method': {'map_point_id': 7, 'address': 'Москва'}}]}

        with patch('requests.post', return_value=FakeResponse(data=info)) as post:
            self.client.get('/api/ozon-logistics/site/point/7/')
            self.client.get('/api/ozon-logistics/site/point/7/')

        self.assertEqual(post.call_count, 1)


@patch.dict('os.environ', CREDS)
class SiteApiOriginTests(TestCase):
    """Чужой домен не должен встроить наш API в свою страницу."""

    def setUp(self):
        cache.clear()
        OzonPickupPoint.objects.create(map_point_id=1, latitude=55.75, longitude=37.61)

    def tearDown(self):
        cache.clear()

    def _points(self, **extra):
        return self.client.get(
            '/api/ozon-logistics/site/points/',
            {'south': 55.5, 'west': 37.3, 'north': 56.0, 'east': 37.9},
            **extra,
        )

    def test_foreign_origin_is_rejected(self):
        response = self._points(HTTP_ORIGIN='https://evil.example')
        self.assertEqual(response.status_code, 403)

    def test_own_site_origin_passes(self):
        response = self._points(HTTP_ORIGIN='https://horse-bio.ru')
        self.assertEqual(response.status_code, 200)

    def test_missing_origin_passes(self):
        """Origin шлёт не каждый клиент — его отсутствие не повод отказывать."""
        self.assertEqual(self._points().status_code, 200)

    def test_availability_limit_is_stricter(self):
        self.assertLess(
            site_api.RATE_LIMITS['availability'], site_api.RATE_LIMITS['quote']
        )


class SiteOrdersTests(TestCase):
    """Создание заказов Ozon по оплаченным заказам сайта."""

    def setUp(self):
        self.product = OzonProduct.objects.create(
            offer_id='13-12VP0100', sku=4797684627, has_fbs_stocks=True
        )
        self.quote = OzonDeliveryQuote.objects.create(
            phone='79166229030',
            items=[{'sku': 4797684627, 'quantity': 1}],
            map_point_id=378617,
            checkout_response=_checkout_response(sku=4797684627),
        )

    def _state(self, *, paid='1', quote_id=None, items=None):
        """State демона 06 — по образцу живого письма заказа 12513118."""
        return {'orders': {'12513118': {'latest': {
            'order_id': '12513118',
            'number': '2086',
            'paid': paid,
            'total': '1580',
            'field': {
                'fio': 'Сергей',
                'familia': 'Сенькин',
                'otcestvo': '',
                'phone': '+79166229030',
                'ozon_quote_id': quote_id if quote_id is not None else str(self.quote.id),
            },
            'items': items if items is not None else [{
                'article': '13-12VP0100',
                'name': 'Желатиновые капсулы',
                'quantity': '1',
                'price': '1580',
            }],
        }}}}

    def _run(self, state, client=None):
        path = Path(tempfile.mkdtemp()) / 'state.json'
        path.write_text(json.dumps(state), encoding='utf-8')
        return site_orders.process_paid_orders(state_path=path, client=client)

    def test_creates_order_for_paid_site_order(self):
        client = FakeOrderClient()
        stats = self._run(self._state(), client=client)

        self.assertEqual(stats['created'], 1)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, OzonDeliveryQuote.STATUS_ORDERED)
        self.assertEqual(self.quote.site_order_id, '12513118')

        # Цена берётся из письма, а не из расчёта — в нём цен нет вовсе
        price = client.order_payloads[0]['splits'][0]['items'][0]['price']
        self.assertEqual(price['units'], 1580)

    def test_unpaid_order_is_skipped(self):
        """Ozon запрещает создавать заказ до подтверждения оплаты."""
        client = FakeOrderClient()
        stats = self._run(self._state(paid=''), client=client)

        self.assertEqual(stats['created'], 0)
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(client.order_payloads, [])

    def test_order_without_quote_field_is_ignored(self):
        state = self._state()
        del state['orders']['12513118']['latest']['field']['ozon_quote_id']
        stats = self._run(state, client=FakeOrderClient())

        self.assertEqual(stats['checked'], 0)

    def test_unknown_quote_id_is_reported(self):
        stats = self._run(
            self._state(quote_id='11111111-1111-1111-1111-111111111111'),
            client=FakeOrderClient(),
        )
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['created'], 0)

    def test_already_ordered_quote_is_not_repeated(self):
        self.quote.status = OzonDeliveryQuote.STATUS_ORDERED
        self.quote.order_number = 'OZ-1'
        self.quote.save()

        client = FakeOrderClient()
        stats = self._run(self._state(), client=client)

        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(client.order_payloads, [])

    def test_unmatched_articles_are_reported_as_failure(self):
        """Без цен заказ создавать нельзя — они обязательны в order/create."""
        stats = self._run(
            self._state(items=[{'article': 'НЕТ-ТАКОГО', 'quantity': '1', 'price': '100'}]),
            client=FakeOrderClient(),
        )
        self.assertEqual(stats['failed'], 1)
        self.assertEqual(stats['created'], 0)

    def test_ozon_failure_is_counted_and_recorded(self):
        client = FakeOrderClient(order_error='HTTP 400: out of stock')
        stats = self._run(self._state(), client=client)

        self.assertEqual(stats['failed'], 1)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.status, OzonDeliveryQuote.STATUS_FAILED)

    def test_missing_state_file_is_not_an_error(self):
        stats = site_orders.process_paid_orders(state_path='/nonexistent/state.json')
        self.assertEqual(stats, {'checked': 0, 'created': 0, 'skipped': 0, 'failed': 0})


class DiscountedPricesTests(TestCase):
    """Скидка сайта живёт только в total — позиции в письме идут по РРЦ."""

    def setUp(self):
        OzonProduct.objects.create(offer_id='ART-1', sku=101, has_fbs_stocks=True)
        OzonProduct.objects.create(offer_id='ART-2', sku=102, has_fbs_stocks=True)

    def test_discount_is_spread_over_positions(self):
        latest = {
            'total': '1880',
            'delivery_cost': '0',
            'items': [{'article': 'ART-1', 'quantity': '1', 'price': '2080'}],
        }
        prices = site_orders._prices_by_sku(latest)
        # В Ozon должна уйти оплаченная сумма, а не РРЦ
        self.assertEqual(prices[101], Decimal('1880.00'))

    def test_delivery_is_excluded_from_discount(self):
        latest = {
            'total': '1100',
            'delivery_cost': '100',
            'items': [{'article': 'ART-1', 'quantity': '1', 'price': '1200'}],
        }
        prices = site_orders._prices_by_sku(latest)
        self.assertEqual(prices[101], Decimal('1000.00'))

    def test_order_without_discount_keeps_prices(self):
        latest = {
            'total': '3000',
            'delivery_cost': '0',
            'items': [
                {'article': 'ART-1', 'quantity': '2', 'price': '1000'},
                {'article': 'ART-2', 'quantity': '1', 'price': '1000'},
            ],
        }
        prices = site_orders._prices_by_sku(latest)
        self.assertEqual(prices[101], Decimal('1000.00'))
        self.assertEqual(prices[102], Decimal('1000.00'))

    def test_unknown_article_is_omitted(self):
        latest = {
            'total': '1000', 'delivery_cost': '0',
            'items': [{'article': 'НЕТ', 'quantity': '1', 'price': '1000'}],
        }
        self.assertEqual(site_orders._prices_by_sku(latest), {})


class MalformedQuoteIdTests(TestCase):
    """Значение приходит из формы сайта — там может оказаться что угодно."""

    def _run(self, quote_id):
        state = {'orders': {'1': {'latest': {
            'paid': '1', 'total': '100', 'items': [],
            'field': {'ozon_quote_id': quote_id, 'phone': '79161112233'},
        }}}}
        path = Path(tempfile.mkdtemp()) / 'state.json'
        path.write_text(json.dumps(state), encoding='utf-8')
        return site_orders.process_paid_orders(state_path=path, client=FakeOrderClient())

    def test_garbage_does_not_break_the_run(self):
        stats = self._run('не-uuid-а-мусор')
        self.assertEqual(stats['skipped'], 1)
        self.assertEqual(stats['failed'], 0)

    def test_null_value_is_treated_as_absent(self):
        stats = self._run(None)
        self.assertEqual(stats['checked'], 0)


class OrderRetryPolicyTests(TestCase):
    def _quote(self, **kwargs):
        defaults = {
            'phone': '79161112233',
            'items': [{'sku': 758646053, 'quantity': 1}],
            'map_point_id': 378617,
            'checkout_response': _checkout_response(),
        }
        return OzonDeliveryQuote.objects.create(**{**defaults, **kwargs})

    def test_timeout_marks_outcome_unknown(self):
        """Ответ потерян — заказ мог создаться, повтор дал бы вторую посылку."""
        quote = self._quote()

        class TimingOutClient:
            def order_create(self, payload):
                raise client_module.OzonLogisticsTimeout('timed out')

        with self.assertRaises(orders.OzonOrderError):
            orders.create_order(
                quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=TimingOutClient()
            )

        quote.refresh_from_db()
        self.assertEqual(quote.status, OzonDeliveryQuote.STATUS_UNKNOWN)
        self.assertFalse(quote.needs_order)

    def test_attempts_are_counted_and_capped(self):
        quote = self._quote()
        client = FakeOrderClient(order_error='HTTP 400: nope')

        for _ in range(OzonDeliveryQuote.MAX_ATTEMPTS):
            with self.assertRaises(orders.OzonOrderError):
                orders.create_order(
                    quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=client
                )

        quote.refresh_from_db()
        self.assertEqual(quote.attempts, OzonDeliveryQuote.MAX_ATTEMPTS)
        self.assertFalse(quote.needs_order)

    def test_successful_order_still_needs_no_retry(self):
        quote = self._quote()
        orders.create_order(
            quote, buyer=BUYER, prices={758646053: Decimal('100')}, client=FakeOrderClient()
        )
        quote.refresh_from_db()
        self.assertFalse(quote.needs_order)


class CancelOrderTests(TestCase):
    """Отмена заказа Ozon. Асинхронная: ответ значит «принято», а не «отменено»."""

    def _quote(self, **kwargs):
        defaults = {
            'phone': '79161112233',
            'items': [{'sku': 758646053, 'quantity': 1}],
            'map_point_id': 378617,
            'checkout_response': _checkout_response(),
            'status': OzonDeliveryQuote.STATUS_ORDERED,
            'order_number': 'OZ-1',
        }
        return OzonDeliveryQuote.objects.create(**{**defaults, **kwargs})

    def test_picks_first_allowed_reason(self):
        class CancelClient:
            def __init__(self):
                self.cancelled = None

            def cancel_check(self, order_number):
                return {'cancellable': True}

            def cancel_reasons_for_order(self, order_number):
                return {'reasons': [{'id': 352}, {'id': 402}]}

            def cancel_order(self, order_number, *, reason_id, reason_message=''):
                self.cancelled = (order_number, reason_id)
                return {'result': True}

        client = CancelClient()
        orders.cancel_order(self._quote(), client=client)
        self.assertEqual(client.cancelled, ('OZ-1', 352))

    def test_explicit_reason_skips_lookup(self):
        """Список причин документация просит не дёргать без надобности."""
        class CancelClient:
            def __init__(self):
                self.reasons_called = False

            def cancel_check(self, order_number):
                return {'cancellable': True}

            def cancel_reasons_for_order(self, order_number):
                self.reasons_called = True
                return {'reasons': []}

            def cancel_order(self, order_number, *, reason_id, reason_message=''):
                return {'result': True}

        client = CancelClient()
        orders.cancel_order(self._quote(), reason_id=402, client=client)
        self.assertFalse(client.reasons_called)

    def test_non_cancellable_order_is_reported(self):
        class CancelClient:
            def cancel_check(self, order_number):
                return {'cancellable': False}

        with self.assertRaises(orders.OzonOrderError) as ctx:
            orders.cancel_order(self._quote(), client=CancelClient())
        self.assertIn('OZ-1', str(ctx.exception))

    def test_quote_without_order_cannot_be_cancelled(self):
        quote = self._quote(status=OzonDeliveryQuote.STATUS_NEW, order_number='')
        with self.assertRaises(orders.OzonOrderError):
            orders.cancel_order(quote, client=None)
