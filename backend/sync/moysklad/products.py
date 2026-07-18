"""
MoySklad API methods for working with products and materials.
"""
import requests

from .base_client import PaginationMixin
from ..logger import setup_logger

logger = setup_logger(__name__)


class ProductsMixin(PaginationMixin):
    """Methods for working with products and materials."""

    def get_product_details(self, product_id):
        """
        Get detailed information about a product.

        Args:
            product_id: Product ID

        Returns:
            Product details dict or empty dict if neither a product nor a
            variant with this ID exists. Other failures are propagated.
        """
        try:
            # Try to get as regular product
            url = f"{self.BASE_URL}/entity/product/{product_id}"
            params = {'expand': 'uom'}
            response = requests.get(url, headers=self.headers, params=params, timeout=60)

            # If not found, try as variant
            if response.status_code == 404:
                url = f"{self.BASE_URL}/entity/variant/{product_id}"
                variant_response = requests.get(url, headers=self.headers, params=params, timeout=60)

                if variant_response.status_code == 404:
                    return {}

                variant_response.raise_for_status()
                product_data = variant_response.json()

                # Get parent product info
                if 'product' in product_data:
                    product_url = product_data['product']['meta']['href']
                    product_response = requests.get(
                        product_url, headers=self.headers, params=params, timeout=60
                    )
                    product_response.raise_for_status()
                    parent_product = product_response.json()

                    # Enrich variant data with parent product data
                    product_data['uom'] = parent_product.get('uom', {})
                    product_data['pathName'] = parent_product.get('pathName', '')
                    product_data['article'] = parent_product.get('article', '')
                    product_data['code'] = parent_product.get('code', '')
                    product_data['description'] = parent_product.get('description', '')

                    product_data['group'] = self._determine_group(product_data)

                return product_data

            response.raise_for_status()
            product_data = response.json()
            product_data['group'] = self._determine_group(product_data)

            return product_data

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for product {product_id}: {str(e)}")
            raise
        except Exception:
            logger.exception(f"Unexpected error for product {product_id}")
            raise

    def _determine_group(self, product_data):
        """
        Determine product group based on pathName.

        Args:
            product_data: Product data dict

        Returns:
            Group name or None
        """
        path_name = product_data.get('pathName', '').lower()
        if 'тара' in path_name:
            return 'Тара'
        elif 'материалы для производства' in path_name:
            return 'Материалы для производства'
        elif 'этикетки' in path_name:
            return 'Этикетки'
        return None

    def get_materials_consumption(self, product_id, quantity):
        """
        Calculate materials consumption for product quantity.

        Args:
            product_id: Product ID
            quantity: Quantity to produce

        Returns:
            List of materials with quantities
        """
        try:
            # Get processing plans for product
            plans = self.get_processing_plan_by_product(product_id)
            if not plans:
                logger.warning(f"No processing plan found for product {product_id}")
                return []

            # Use first available plan
            plan = plans[0]
            materials = []

            # Get materials from plan
            if 'materials' in plan and 'rows' in plan['materials']:
                for material in plan['materials']['rows']:
                    if 'assortment' not in material:
                        continue

                    mat_quantity = float(material.get('quantity', 0)) * quantity
                    materials.append({
                        'material': material['assortment'],
                        'quantity': mat_quantity
                    })

            return materials

        except Exception as e:
            logger.error(f"Error calculating materials consumption: {str(e)}")
            return []

    def get_product_folders(self):
        """Get all product folders with pagination."""
        url = f"{self.BASE_URL}/entity/productfolder"
        return self.paginated_request(url, limit=1000)

    def get_materials_updated_since(self, since_date):
        """
        Get materials updated since given date.

        Args:
            since_date: Datetime to filter from

        Returns:
            List of updated materials
        """
        url = f"{self.BASE_URL}/entity/product"
        params = {
            "filter": f"updated>={since_date.strftime('%Y-%m-%d %H:%M:%S')}",
            "expand": "uom"
        }
        return self.paginated_request(url, params, limit=1000)
