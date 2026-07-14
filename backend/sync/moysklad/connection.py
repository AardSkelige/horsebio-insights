# sync/moysklad/connection.py
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError
from ..logger import setup_logger
from .shipments import ShipmentsMixin
from .supplies import SuppliesMixin
from .plans import PlansMixin
from .products import ProductsMixin
from .purchases import PurchaseOrderMixin
from .inventories import InventoriesMixin

logger = setup_logger(__name__)

# Опциональный импорт tenacity для retry logic
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False
    logger.warning("tenacity not installed - API retry logic disabled. Run: pip install tenacity")


def _log_retry(retry_state):
    """Логирование повторных попыток API запросов"""
    exception = retry_state.outcome.exception() if retry_state.outcome else 'unknown error'
    logger.warning(
        f"МойСклад API retry {retry_state.attempt_number}/3: {exception}"
    )


def _with_retry(func):
    """Декоратор для добавления retry logic если tenacity доступен"""
    if TENACITY_AVAILABLE:
        return retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((RequestException, Timeout, ConnectionError)),
            before_sleep=_log_retry,
            reraise=True
        )(func)
    return func


class MoySkladAPIClient(ShipmentsMixin, SuppliesMixin, PlansMixin, ProductsMixin, PurchaseOrderMixin, InventoriesMixin):
    """Основной класс для работы с МойСклад API"""
    BASE_URL = "https://api.moysklad.ru/api/remap/1.2"

    def __init__(self, token):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept-Encoding": "gzip"
        }

    def get(self, url, **kwargs):
        """Выполнение GET-запроса к API с автоматическими повторами при ошибках сети"""
        return self._get_impl(url, **kwargs)

    @staticmethod
    @_with_retry
    def _get_impl_with_retry(url, **kwargs):
        """Внутренний метод с retry"""
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 60
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        return response

    def _get_impl(self, url, **kwargs):
        """Выполнение GET-запроса"""
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 60

        try:
            if TENACITY_AVAILABLE:
                return self._get_impl_with_retry(url, **kwargs)
            else:
                response = requests.get(url, **kwargs)
                response.raise_for_status()
                return response
        except Exception as e:
            logger.error(f"Error in GET request to {url}: {str(e)}")
            raise