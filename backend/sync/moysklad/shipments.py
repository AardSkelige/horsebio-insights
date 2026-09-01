"""
MoySklad API methods for working with shipments (отгрузки/demands).
"""
from datetime import datetime, timedelta

from .base_client import PaginationMixin, format_date_filter
from ..logger import setup_logger

logger = setup_logger(__name__)


class ShipmentsMixin(PaginationMixin):
    """Methods for working with shipments."""

    def get_shipments_for_period(self, start_date, end_date):
        """
        Get shipments for specific period with basic information.

        Args:
            start_date: Period start datetime
            end_date: Period end datetime

        Returns:
            List of shipment records
        """
        url = f"{self.BASE_URL}/entity/demand"
        params = {
            "filter": format_date_filter(start_date, end_date),
            "select": "id,name,updated,moment,agent.id,agent.name",
            "order": "moment,desc"
        }
        return self.paginated_request(url, params, limit=1000)

    def get_shipment_details(self, shipment_id):
        """
        Get detailed information about a shipment.

        Args:
            shipment_id: Shipment ID

        Returns:
            Shipment details dict or None if error
        """
        url = f"{self.BASE_URL}/entity/demand/{shipment_id}"
        params = {"expand": "agent,positions.assortment,salesChannel"}
        return self.single_request(url, params)

    def get_shipment_sales_channels(self, start_date, end_date):
        """
        Get shipment ids with their sales channel ids for specific period.

        Списочный запрос отдаёт канал продаж прямо в отгрузке, поэтому для
        проставления канала не нужны детали документа с позициями.

        Args:
            start_date: Period start datetime
            end_date: Period end datetime

        Returns:
            List of (shipment_id, sales_channel_id or None) tuples
        """
        url = f"{self.BASE_URL}/entity/demand"
        params = {
            "filter": format_date_filter(start_date, end_date),
            "order": "moment,desc"
        }

        def extract(row):
            channel = row.get('salesChannel') or {}
            href = channel.get('meta', {}).get('href', '')
            return row['id'], href.rsplit('/', 1)[-1] if href else None

        return self.paginated_request(url, params, limit=1000, transform=extract)

    def get_sales_channels(self):
        """
        Get all sales channels.

        Returns:
            List of sales channel records
        """
        url = f"{self.BASE_URL}/entity/saleschannel"
        return self.paginated_request(url, {}, limit=1000)

    def get_shipments(self):
        """Get all shipments for last 365 days."""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        return self.get_shipments_for_period(start_date, end_date)
