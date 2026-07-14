"""
MoySklad inventory mixin.

Key findings from API testing:
- productFolder href filter returns 412 — use pathName string filter instead
- pathName is a filterable String field on /entity/product
- ~= operator means "starts with"
- Positions in inventory documents use assortment type="product" (no variants in this account)
- Inventories are fetched via /entity/inventory?filter=moment>=...
"""
from datetime import datetime
from typing import Dict, List, Optional

from ..logger import setup_logger
from .base_client import PaginationMixin

logger = setup_logger(__name__)

# pathName filter → display category for the UI
# pathName on a product = the path of its parent folder
# e.g. product in "Товары/ArtroPro" has pathName="Товары/ArtroPro"
# e.g. product directly in "Тара" has pathName="Тара"
PATHNAME_FILTERS = [
    # filter_string,                              category label
    # МойСклад excludes archived products by default (no extra filter needed)
    ("pathName~=Товары/",                        "Товары"),
    ("pathName=Тара",                            "Тара"),
    ("pathName=Этикетки",                        "Этикетки"),
    ("pathName~=Материалы для производства",     "Материалы"),
]


class InventoriesMixin(PaginationMixin):

    def get_monitored_products(self) -> List[dict]:
        """
        Returns all monitored products with '_category' field added.
        Uses pathName-based filtering (productFolder href gives 412).
        """
        seen_ids = set()
        all_products: List[dict] = []

        for filter_str, category in PATHNAME_FILTERS:
            url = f"{self.BASE_URL}/entity/product"
            products = self.paginated_request(url, {"filter": filter_str})
            for p in products:
                pid = p.get("id")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    p["_category"] = category
                    all_products.append(p)
            logger.info(f"Fetched {len(products)} products for category '{category}'")

        logger.info(f"Total monitored products: {len(all_products)}")
        return all_products

    def get_inventoried_products_map(self, from_date: datetime,
                                      to_date: Optional[datetime] = None) -> Dict[str, dict]:
        """
        Returns {product_id: {'count': int, 'last_date': aware datetime}}
        for all inventory positions in documents dated >= from_date (and <= to_date if given).
        """
        from django.utils import timezone

        url = f"{self.BASE_URL}/entity/inventory"
        from_str = from_date.strftime("%Y-%m-%d %H:%M:%S")
        filter_str = f"moment>={from_str}"
        if to_date:
            to_str = to_date.strftime("%Y-%m-%d %H:%M:%S")
            filter_str += f";moment<={to_str}"
        inventories = self.paginated_request(url, {"filter": filter_str})

        logger.info(f"Processing {len(inventories)} inventory documents since {from_str}")

        result: Dict[str, dict] = {}

        for inventory in inventories:
            inv_id = inventory.get("id")
            inv_moment_str = inventory.get("moment", "")

            inv_dt = None
            if inv_moment_str:
                try:
                    inv_dt = datetime.strptime(inv_moment_str[:19], "%Y-%m-%d %H:%M:%S")
                    inv_dt = timezone.make_aware(inv_dt)
                except (ValueError, Exception):
                    pass

            positions_url = f"{self.BASE_URL}/entity/inventory/{inv_id}/positions"
            positions = self.paginated_request(positions_url, {})

            for pos in positions:
                assortment = pos.get("assortment", {})
                href = assortment.get("meta", {}).get("href", "")
                product_id = href.split("/")[-1] if href else None

                if not product_id:
                    continue

                if product_id not in result:
                    result[product_id] = {"count": 0, "last_date": None}

                result[product_id]["count"] += 1
                if inv_dt and (result[product_id]["last_date"] is None
                               or inv_dt > result[product_id]["last_date"]):
                    result[product_id]["last_date"] = inv_dt

        logger.info(f"Unique inventoried products: {len(result)}")
        return result
