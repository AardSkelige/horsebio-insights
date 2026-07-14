"""
MoySklad API methods for working with purchase orders (заказы поставщикам).
"""
from .base_client import PaginationMixin, format_date_filter
from ..logger import setup_logger

logger = setup_logger(__name__)


class PurchaseOrderMixin(PaginationMixin):
    """Methods for working with purchase orders."""

    def get_purchase_orders_for_period(self, start_date, end_date):
        """
        Get purchase orders for specific period.

        Args:
            start_date: Period start datetime
            end_date: Period end datetime

        Returns:
            List of purchase order records
        """
        url = f"{self.BASE_URL}/entity/purchaseorder"
        params = {
            "filter": format_date_filter(start_date, end_date),
            "select": "id,name,updated,moment,agent.id,agent.name,state.name,sum,created",
            "order": "moment,desc",
            "expand": "agent,state"
        }
        return self.paginated_request(url, params, limit=1000)

    def get_purchase_order_details(self, order_id):
        """
        Get detailed information about a purchase order.

        Args:
            order_id: Purchase order ID

        Returns:
            Purchase order details dict or None if error
        """
        url = f"{self.BASE_URL}/entity/purchaseorder/{order_id}"
        params = {"expand": "agent,positions.assortment,state,supplies"}
        return self.single_request(url, params)
