"""Запросы к JSON API МойСклад с учётом лимита запросов.

Зачем слой. МойСклад выдаёт каждому пользователю корзину в 45 единиц лимита,
которая обновляется каждые 3 секунды. Запрос списывает из неё не единицу, а свой
вес: с 12.05.2026 обычный запрос стоит 2 единицы, с 01.09.2026 — 3, с 01.12.2026 — 4;
/report/stock/all и /report/stock/bystore стоят 5 всегда. Когда корзина пуста,
приходит 429, а если ловить 429 больше 200 раз в минуту в течение часа, МойСклад
отключает аккаунту доступ к API до обращения в поддержку.

Что делает слой:
  * ждёт ровно столько, сколько просит сервер в X-Lognex-Retry-After, и повторяет
    запрос — вместо падения скрипта или слепого экспоненциального ретрая;
  * следит за X-RateLimit-Remaining и притормаживает ВСЕ запросы процесса, когда
    в корзине осталось меньше веса одного тяжёлого запроса — так до 429 обычно
    просто не доходит;
  * повторяет запрос при обрыве связи и таймауте.

Интерфейс намеренно повторяет requests: get/post/put/delete(url, **kwargs)
возвращают requests.Response, статус не проверяется. Это позволяет подключать
слой заменой импорта и не трогать вызывающий код.

Пауза общая на процесс: у cron-скрипта это его единственный поток, у Django —
все потоки gunicorn, которые ходят под одним токеном и делят одну корзину.
"""

import logging
import random
import threading
import time

import requests

logger = logging.getLogger(__name__)

# Окно лимита, мс. Значение дублируется сервером в X-Lognex-Retry-TimeInterval.
WINDOW_MS = 3000

# Порог, ниже которого не начинаем новый запрос, а ждём обновления корзины.
# 10 единиц — это вес двух запросов к /report/stock/all, самых дорогих в API.
RESERVE_UNITS = 10

# Попыток на один запрос (первая + повторы) при 429 и при сетевых ошибках.
MAX_ATTEMPTS = 6

# Верхняя граница одной паузы, с. Страховка от абсурдного значения в заголовке.
MAX_SLEEP_S = 30.0

DEFAULT_TIMEOUT = 60

_lock = threading.Lock()
# Момент по монотонным часам, раньше которого новые запросы не начинаем.
_pause_until = 0.0


def _sleep_budget(seconds: float, reason: str) -> None:
    """Притормозить все запросы процесса на seconds."""
    global _pause_until
    seconds = min(max(seconds, 0.0), MAX_SLEEP_S)
    if seconds <= 0:
        return
    with _lock:
        _pause_until = max(_pause_until, time.monotonic() + seconds)
    logger.warning("МойСклад: лимит запросов, пауза %.2f с (%s)", seconds, reason)


def _await_budget() -> None:
    """Дождаться, пока корзина лимита снова позволит запрос."""
    while True:
        with _lock:
            delay = _pause_until - time.monotonic()
        if delay <= 0:
            return
        time.sleep(min(delay, MAX_SLEEP_S))


def _header_ms(response, name: str) -> float | None:
    """Заголовок с миллисекундами → секунды. None, если заголовка нет."""
    raw = response.headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw) / 1000
    except (TypeError, ValueError):
        return None


def _note_remaining(response) -> None:
    """Осталось меньше RESERVE_UNITS — тормозим до обновления корзины."""
    raw = response.headers.get("X-RateLimit-Remaining")
    if raw is None:
        return
    try:
        remaining = int(raw)
    except (TypeError, ValueError):
        return
    if remaining >= RESERVE_UNITS:
        return
    reset_s = _header_ms(response, "X-Lognex-Reset") or WINDOW_MS / 1000
    _sleep_budget(reset_s, f"осталось {remaining} единиц лимита")


def _retry_after_s(response, attempt: int) -> float:
    """Сколько ждать после 429: сервер знает точно, иначе целое окно.

    Джиттер нужен, когда в 429 упирается сразу несколько потоков: без него они
    просыпаются одновременно и снова выбирают корзину залпом.
    """
    wait = (
        _header_ms(response, "X-Lognex-Retry-After")
        or _header_ms(response, "X-Lognex-Retry-TimeInterval")
        or WINDOW_MS / 1000
    )
    return wait + random.uniform(0, 0.25 * (attempt + 1))


def request(method: str, url: str, **kwargs) -> requests.Response:
    """Запрос к МойСклад с ожиданием лимита и повторами. Статус не проверяется."""
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT)

    last_error = None
    for attempt in range(MAX_ATTEMPTS):
        _await_budget()
        try:
            response = requests.request(method, url, **kwargs)
        except (requests.Timeout, requests.ConnectionError) as exc:
            # Сеть, а не лимит: ждём сами, по нарастающей.
            last_error = exc
            delay = min(2 ** attempt, MAX_SLEEP_S) + random.uniform(0, 0.5)
            logger.warning(
                "МойСклад: %s, повтор %d/%d через %.1f с",
                type(exc).__name__, attempt + 1, MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)
            continue

        if response.status_code == 429:
            # Последнюю попытку возвращаем как есть: вызывающий сам решит, что
            # делать с 429 — молча съеденная ошибка хуже явной.
            if attempt == MAX_ATTEMPTS - 1:
                logger.error("МойСклад: 429 после %d попыток, %s", MAX_ATTEMPTS, url)
                return response
            _sleep_budget(_retry_after_s(response, attempt), f"429 на {url}")
            continue

        _note_remaining(response)
        return response

    raise requests.ConnectionError(f"МойСклад недоступен после {MAX_ATTEMPTS} попыток: {last_error}")


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs) -> requests.Response:
    return request("PUT", url, **kwargs)


def delete(url: str, **kwargs) -> requests.Response:
    return request("DELETE", url, **kwargs)
