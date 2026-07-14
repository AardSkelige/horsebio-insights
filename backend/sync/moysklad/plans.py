"""
MoySklad API methods for working with processing plans (техкарты).
"""
from .base_client import PaginationMixin
from ..logger import setup_logger

logger = setup_logger(__name__)


class PlansMixin(PaginationMixin):
    """Methods for working with processing plans."""

    def get_all_processing_plans(self):
        """
        Get all processing plans with basic information.

        Returns:
            List of processing plan records
        """
        url = f"{self.BASE_URL}/entity/processingplan"
        params = {"select": "id,name,updated,created"}
        return self.paginated_request(url, params, limit=1000)

    def get_processing_plan(self, plan_id):
        """
        Get specific processing plan by ID.

        Args:
            plan_id: Processing plan ID

        Returns:
            Processing plan dict or empty dict if error
        """
        url = f"{self.BASE_URL}/entity/processingplan/{plan_id}"
        result = self.single_request(url)
        if result:
            logger.debug(f"Retrieved processing plan: {result.get('name', 'Unknown')}")
        return result or {}

    def get_processing_plan_materials(self, plan_id):
        """
        Get materials for specific processing plan.

        Args:
            plan_id: Processing plan ID

        Returns:
            List of material records
        """
        url = f"{self.BASE_URL}/entity/processingplan/{plan_id}/materials"
        result = self.single_request(url)
        materials = result.get('rows', []) if result else []
        logger.debug(f"Retrieved {len(materials)} materials for plan {plan_id}")
        return materials

    def get_processing_plan_products(self, plan_id):
        """
        Get products for specific processing plan.

        Args:
            plan_id: Processing plan ID

        Returns:
            List of product records
        """
        url = f"{self.BASE_URL}/entity/processingplan/{plan_id}/products"
        result = self.single_request(url)
        products = result.get('rows', []) if result else []
        logger.debug(f"Retrieved {len(products)} products for plan {plan_id}")
        return products

    def get_processing_plan_by_product(self, product_id):
        """
        Get processing plans for specific product.

        Args:
            product_id: Product ID

        Returns:
            List of processing plans containing this product
        """
        url = f"{self.BASE_URL}/entity/processingplan"
        params = {
            "filter": f"products.id={product_id}",
            "expand": "materials,products"
        }
        result = self.single_request(url, params)
        return result.get('rows', []) if result else []
