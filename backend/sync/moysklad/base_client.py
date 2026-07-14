"""
Base client functionality for MoySklad API.
Provides common pagination and request methods used by all mixins.
"""
from typing import Any, Callable, Dict, List, Optional

import requests

from ..logger import setup_logger

logger = setup_logger(__name__)


class PaginationMixin:
    """
    Mixin providing paginated request functionality for MoySklad API.

    This mixin consolidates the repeated pagination pattern found in
    shipments.py, supplies.py, purchases.py, products.py, etc.

    Requires the class to have:
        - self.headers: dict with Authorization header
        - BASE_URL: class attribute with API base URL
        - self.get(): method for making GET requests (optional, falls back to requests.get)

    Example usage:
        class ShipmentsMixin(PaginationMixin):
            def get_shipments_for_period(self, start_date, end_date):
                url = f"{self.BASE_URL}/entity/demand"
                params = {
                    "filter": f"moment>={start_date}...",
                    "order": "moment,desc"
                }
                return self.paginated_request(url, params)
    """

    def paginated_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        limit: int = 1000,
        data_key: str = 'rows',
        max_items: Optional[int] = None,
        transform: Optional[Callable[[Dict], Any]] = None
    ) -> List[Any]:
        """
        Execute a paginated GET request to the MoySklad API.

        Args:
            url: Full API endpoint URL
            params: Query parameters (offset and limit will be added/overwritten)
            limit: Number of items per page (max 1000 for MoySklad)
            data_key: Key in response JSON containing the data array (default: 'rows')
            max_items: Optional maximum number of items to fetch
            transform: Optional function to transform each item

        Returns:
            List of all items from all pages

        Example:
            >>> url = f"{self.BASE_URL}/entity/demand"
            >>> params = {"filter": "moment>=2024-01-01"}
            >>> all_shipments = self.paginated_request(url, params)
        """
        if params is None:
            params = {}

        all_items = []
        offset = 0

        while True:
            try:
                # Set pagination params
                page_params = params.copy()
                page_params['limit'] = limit
                page_params['offset'] = offset

                # Use self.get() if available (with retry logic), else use requests.get
                if hasattr(self, 'get'):
                    response = self.get(url, headers=self.headers, params=page_params)
                else:
                    response = requests.get(url, headers=self.headers, params=page_params, timeout=60)
                    response.raise_for_status()

                data = response.json()
                rows = data.get(data_key, [])

                if not rows:
                    break

                # Apply transformation if provided
                if transform:
                    rows = [transform(item) for item in rows]

                all_items.extend(rows)

                # Check if we've reached the maximum
                if max_items and len(all_items) >= max_items:
                    all_items = all_items[:max_items]
                    break

                # Check if we've fetched all items
                if len(rows) < limit:
                    break

                offset += limit
                logger.debug(f"Retrieved {len(all_items)} items so far from {url}...")

            except Exception as e:
                logger.error(f"Error fetching data at offset {offset} from {url}: {str(e)}")
                break

        return all_items

    def single_request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a single GET request to the MoySklad API.

        Args:
            url: Full API endpoint URL
            params: Query parameters

        Returns:
            Response JSON or None if request fails
        """
        try:
            if hasattr(self, 'get'):
                response = self.get(url, headers=self.headers, params=params)
            else:
                response = requests.get(url, headers=self.headers, params=params, timeout=60)
                response.raise_for_status()

            return response.json()
        except Exception as e:
            logger.error(f"Error in request to {url}: {str(e)}")
            return None


def format_date_filter(start_date, end_date, field: str = 'moment') -> str:
    """
    Format date range filter for MoySklad API.

    Args:
        start_date: Start datetime object
        end_date: End datetime object
        field: Field name to filter on (default: 'moment')

    Returns:
        Filter string for MoySklad API

    Example:
        >>> filter_str = format_date_filter(start, end)
        >>> # Returns: "moment>=2024-01-01 00:00:00;moment<=2024-01-31 23:59:59"
    """
    start_str = start_date.strftime('%Y-%m-%d %H:%M:%S')
    end_str = end_date.strftime('%Y-%m-%d %H:%M:%S')
    return f"{field}>={start_str};{field}<={end_str}"
