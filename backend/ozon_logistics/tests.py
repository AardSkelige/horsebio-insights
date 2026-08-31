import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings
from django.utils import timezone

from ozon_logistics.models import OzonAuthState, OzonOAuthToken
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
        self.assertIn('seller-api.ozon-logistics', query['scope'][0].split(' '))

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
