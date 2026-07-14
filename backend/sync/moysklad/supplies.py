"""
MoySklad API methods for working with supplies (поставки).
"""
from datetime import datetime, timedelta

from .base_client import PaginationMixin, format_date_filter
from ..logger import setup_logger

logger = setup_logger(__name__)


class SuppliesMixin(PaginationMixin):
    """Methods for working with supplies."""

    def get_supplies_for_period(self, start_date, end_date):
        """
        Get supplies for specific period with basic information.

        Args:
            start_date: Period start datetime
            end_date: Period end datetime

        Returns:
            List of supply records
        """
        url = f"{self.BASE_URL}/entity/supply"
        params = {
            "filter": format_date_filter(start_date, end_date),
            "select": "id,name,updated,moment,agent.id,agent.name",
            "order": "moment,desc"
        }
        return self.paginated_request(url, params, limit=1000)

    def get_supply_details(self, supply_id):
        """
        Get detailed information about a supply.

        Args:
            supply_id: Supply ID

        Returns:
            Supply details dict or None if error
        """
        url = f"{self.BASE_URL}/entity/supply/{supply_id}"
        params = {"expand": "agent,positions.assortment"}
        return self.single_request(url, params)

    def get_supplies(self):
        """Get all supplies for last 365 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        return self.get_supplies_for_period(start_date, end_date)
