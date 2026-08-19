# sync/moysklad/connection.py
from msapi import http as ms_http

from ..logger import setup_logger
from .shipments import ShipmentsMixin
from .supplies import SuppliesMixin
from .plans import PlansMixin
from .products import ProductsMixin
from .purchases import PurchaseOrderMixin
from .inventories import InventoriesMixin

logger = setup_logger(__name__)


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
        """GET к API. Ожидание лимита, 429 и повторы при обрыве связи — в ms_http."""
        try:
            response = ms_http.get(url, **kwargs)
            response.raise_for_status()
            return response
        except Exception as e:
            logger.error(f"Error in GET request to {url}: {str(e)}")
            raise
