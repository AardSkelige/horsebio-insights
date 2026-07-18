# sync/cache.py

import time
from asgiref.sync import sync_to_async
from django.db import DatabaseError
from .logger import logger
from .models import ProcessingPlanProduct


class ProductDetailsFetchError(RuntimeError):
    """Temporary/API failure while resolving a product; safe to retry later."""


class MaterialRegistry:
    """Кэш для материалов техкарт"""
    def __init__(self):
        self.product_materials = {}

    @sync_to_async
    def load_existing_materials(self):
        """Загружает материалы в кэш"""
        product_materials = ProcessingPlanProduct.objects.select_related(
            'processing_plan', 'product'
        ).prefetch_related(
            'processing_plan__materials',
            'processing_plan__materials__material'
        )

        for ppp in product_materials:
            product_id = ppp.product.external_id
            self.product_materials[product_id] = [
                {
                    'material': m.material,
                    'quantity': float(m.quantity)
                }
                for m in ppp.processing_plan.materials.all()
            ]

    def get_materials_for_product(self, product_id):
        """Получает материалы для продукта"""
        if product_id not in self.product_materials:
            try:
                ppp = ProcessingPlanProduct.objects.select_related(
                    'processing_plan', 'product'
                ).prefetch_related(
                    'processing_plan__materials',
                    'processing_plan__materials__material'
                ).filter(product__external_id=product_id).first()

                if ppp:
                    self.product_materials[product_id] = [
                        {
                            'material': m.material,
                            'quantity': float(m.quantity)
                        }
                        for m in ppp.processing_plan.materials.all()
                    ]
                else:
                    self.product_materials[product_id] = []
            except Exception as e:
                logger.error(f"Error getting materials for product {product_id}: {str(e)}")
                if isinstance(e, DatabaseError):
                    raise
                return []

        return self.product_materials.get(product_id, [])


class ProductCache:
    """Кэш для продуктов и материалов"""
    def __init__(self):
        self.cache = {}
        self.missed_products = set()

    def get_product_details(self, client, product_id, is_material=False):
        """Получает детали продукта/материала"""
        if product_id in self.missed_products:
            return None

        if product_id not in self.cache:
            try:
                details = client.get_product_details(product_id)
                if details:
                    self.cache[product_id] = details
                else:
                    self.missed_products.add(product_id)
                    logger.warning(f"No details found for {'material' if is_material else 'product'}: {product_id}")
                    return None
            except Exception as e:
                logger.error(f"Error fetching {'material' if is_material else 'product'} details: {str(e)}")
                # A network/API failure is not proof that the product is absent.
                # Do not poison the negative cache and let the sync fail visibly.
                raise ProductDetailsFetchError(str(e)) from e

        return self.cache.get(product_id)

    def bulk_prefetch(self, client, ids, is_material=False):
        """Пакетная загрузка продуктов/материалов"""
        start_time = time.time()

        for product_id in ids:
            if product_id not in self.cache and product_id not in self.missed_products:
                self.get_product_details(client, product_id, is_material)

        end_time = time.time()
        logger.info(f"Prefetch completed in {end_time - start_time:.2f} seconds")
