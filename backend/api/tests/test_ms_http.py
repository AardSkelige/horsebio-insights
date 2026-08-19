"""Тесты слоя запросов к МойСклад: лимит запросов, 429, обрывы связи.

Проверяем поведение, ради которого слой заведён: 429 не выпускается наружу как
исключение, а превращается в ожидание и повтор; сервер сам говорит, сколько
ждать; истощённая корзина лимита тормозит следующий запрос.
"""

from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from msapi import http as ms_http


def _response(status=200, remaining=45, headers=None):
    response = MagicMock(spec=requests.Response)
    response.status_code = status
    response.headers = {"X-RateLimit-Remaining": str(remaining), "X-RateLimit-Limit": "45"}
    if headers:
        response.headers.update(headers)
    return response


class MsHttpTests(SimpleTestCase):
    """Часы подменены на фиктивные: sleep не тормозит тесты, а двигает время,
    поэтому паузы слоя проверяются по их длительности, а не по ожиданию."""

    START = 1000.0

    def setUp(self):
        # Пауза глобальна на процесс — иначе тесты влияют друг на друга.
        ms_http._pause_until = 0.0
        self.now = self.START
        patchers = [
            patch("msapi.http.time.monotonic", lambda: self.now),
            patch("msapi.http.time.sleep", self._advance),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        ms_http._pause_until = 0.0

    def _advance(self, seconds):
        self.now += seconds

    @property
    def waited(self):
        return self.now - self.START

    @patch("msapi.http.requests.request")
    def test_429_is_retried_not_raised(self, mock_request):
        mock_request.side_effect = [_response(status=429), _response(status=200)]

        response = ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_request.call_count, 2)

    @patch("msapi.http.requests.request")
    def test_waits_as_long_as_server_asks(self, mock_request):
        mock_request.side_effect = [
            _response(status=429, headers={"X-Lognex-Retry-After": "2500"}),
            _response(status=200),
        ]

        ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        # Сервер попросил 2,5 с — ждём не меньше (сверху джиттер), но и не сутки.
        self.assertGreaterEqual(self.waited, 2.5)
        self.assertLess(self.waited, 3.5)

    @patch("msapi.http.requests.request")
    def test_429_returned_to_caller_after_all_attempts(self, mock_request):
        mock_request.return_value = _response(status=429)

        response = ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(response.status_code, 429)
        self.assertEqual(mock_request.call_count, ms_http.MAX_ATTEMPTS)

    @patch("msapi.http.requests.request")
    def test_low_remaining_pauses_next_request(self, mock_request):
        mock_request.return_value = _response(status=200, remaining=4)

        ms_http.get("https://api.moysklad.ru/api/remap/1.2/report/stock/all")

        # Корзина почти пуста: следующий запрос должен ждать обновления окна.
        self.assertGreaterEqual(ms_http._pause_until - self.now, ms_http.WINDOW_MS / 1000)

    @patch("msapi.http.requests.request")
    def test_full_remaining_does_not_pause(self, mock_request):
        mock_request.return_value = _response(status=200, remaining=43)

        ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(ms_http._pause_until, 0.0)
        self.assertEqual(self.waited, 0.0)

    @patch("msapi.http.requests.request")
    def test_connection_error_is_retried(self, mock_request):
        mock_request.side_effect = [requests.ConnectionError("boom"), _response(status=200)]

        response = ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(response.status_code, 200)

    @patch("msapi.http.requests.request")
    def test_network_failure_raises_after_all_attempts(self, mock_request):
        mock_request.side_effect = requests.ConnectionError("boom")

        with self.assertRaises(requests.ConnectionError):
            ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(mock_request.call_count, ms_http.MAX_ATTEMPTS)

    @patch("msapi.http.requests.request")
    def test_http_errors_are_not_retried(self, mock_request):
        """404 — это ответ, а не троттлинг: повторять его бессмысленно."""
        mock_request.return_value = _response(status=404)

        response = ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(mock_request.call_count, 1)

    @patch("msapi.http.requests.request")
    def test_timeout_default_is_set(self, mock_request):
        mock_request.return_value = _response()

        ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product")

        self.assertEqual(mock_request.call_args.kwargs["timeout"], ms_http.DEFAULT_TIMEOUT)

    @patch("msapi.http.requests.request")
    def test_caller_timeout_wins(self, mock_request):
        mock_request.return_value = _response()

        ms_http.get("https://api.moysklad.ru/api/remap/1.2/entity/product", timeout=15)

        self.assertEqual(mock_request.call_args.kwargs["timeout"], 15)

    @patch("msapi.http.requests.request")
    def test_methods_map_to_verbs(self, mock_request):
        mock_request.return_value = _response()

        for func, verb in ((ms_http.get, "GET"), (ms_http.post, "POST"),
                           (ms_http.put, "PUT"), (ms_http.delete, "DELETE")):
            func("https://api.moysklad.ru/api/remap/1.2/entity/product")
            self.assertEqual(mock_request.call_args.args[0], verb)
