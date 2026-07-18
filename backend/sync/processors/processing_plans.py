# sync/processors/processing_plans.py

from django.db import DatabaseError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from sync.models import (
    ProcessingPlan, ProcessingPlanMaterial, ProcessingPlanProduct,
    RawMaterial, Product
)
from sync.logger import logger, structured_logger
from sync.sync_task import TaskStatus
from sync.cache import ProductDetailsFetchError
from sync.utils import get_group_from_pathname


class ProcessingPlanStorage:
    def __init__(self, product_cache):
        self.product_cache = product_cache

    @sync_to_async(thread_sensitive=True)
    def save_processing_plan(self, plan_data: dict, moysklad_updated: str = None):
        """Сохранение техкарты"""
        try:
            with transaction.atomic():
                defaults = {
                    'name': plan_data.get('name', ''),
                }
                if moysklad_updated:
                    parsed_date = parse_datetime(moysklad_updated)
                    if parsed_date and timezone.is_naive(parsed_date):
                        parsed_date = timezone.make_aware(parsed_date)
                    defaults['moysklad_updated'] = parsed_date

                processing_plan, _ = ProcessingPlan.objects.update_or_create(
                    external_id=plan_data['id'],
                    defaults=defaults
                )
                return processing_plan
        except Exception as e:
            logger.error(f"Error saving processing plan: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return None

    @sync_to_async
    def save_processing_plan_materials(self, processing_plan, materials, client):
        """Сохранение материалов техкарты"""
        try:
            saved_count = 0
            with transaction.atomic():
                ProcessingPlanMaterial.objects.filter(processing_plan=processing_plan).delete()

                for material_data in materials:
                    if not isinstance(material_data, dict):
                        logger.error(f"Invalid material data format: {material_data}")
                        continue

                    assortment = material_data.get('assortment')
                    if not assortment or not isinstance(assortment, dict):
                        logger.error(f"Invalid assortment data: {material_data}")
                        continue

                    material_id = assortment.get('meta', {}).get('href', '').split('/')[-1]
                    if not material_id:
                        logger.error(f"Could not extract material ID from: {assortment}")
                        continue

                    material_details = self.product_cache.get_product_details(
                        client,
                        material_id,
                        is_material=True
                    )

                    if not material_details:
                        logger.warning(f"No details found for material ID: {material_id}")
                        continue

                    raw_material, _ = RawMaterial.objects.get_or_create(
                        external_id=material_id,
                        defaults={
                            'name': material_details.get('name', assortment.get('name', '')),
                            'uom_name': material_details.get('uom', {}).get('name'),
                            'group': get_group_from_pathname(material_details.get('pathName'))
                        }
                    )

                    quantity = material_data.get('quantity', 0)
                    ProcessingPlanMaterial.objects.create(
                        processing_plan=processing_plan,
                        material=raw_material,
                        quantity=quantity
                    )
                    saved_count += 1

                return saved_count

        except Exception as e:
            logger.error(f"Error saving processing plan materials: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return 0

    @sync_to_async
    def save_processing_plan_products(self, processing_plan, products, client):
        """Сохранение продуктов техкарты"""
        try:
            saved_count = 0
            with transaction.atomic():
                ProcessingPlanProduct.objects.filter(processing_plan=processing_plan).delete()

                for product_data in products:
                    if not isinstance(product_data, dict):
                        logger.error(f"Invalid product data format: {product_data}")
                        continue

                    assortment = product_data.get('assortment')
                    if not assortment or not isinstance(assortment, dict):
                        logger.error(f"Invalid assortment data: {product_data}")
                        continue

                    product_id = assortment.get('meta', {}).get('href', '').split('/')[-1]
                    if not product_id:
                        logger.error(f"Could not extract product ID from: {assortment}")
                        continue

                    product_details = self.product_cache.get_product_details(
                        client,
                        product_id,
                        is_material=False
                    )

                    if not product_details:
                        logger.warning(f"No details found for product ID: {product_id}")
                        continue

                    path_name = product_details.get('pathName', '')
                    path_parts = path_name.split('/') if path_name else []
                    group = get_group_from_pathname(path_name)
                    subgroup = path_parts[1].strip() if len(path_parts) > 1 else None

                    product, _ = Product.objects.get_or_create(
                        external_id=product_id,
                        defaults={
                            'name': product_details.get('name', assortment.get('name', '')),
                            'uom_name': product_details.get('uom', {}).get('name'),
                            'group': group,
                            'subgroup': subgroup,
                            'article': product_details.get('article'),
                            'code': product_details.get('code'),
                            'description': product_details.get('description')
                        }
                    )

                    quantity = product_data.get('quantity', 0)
                    ProcessingPlanProduct.objects.create(
                        processing_plan=processing_plan,
                        product=product,
                        quantity=quantity
                    )
                    saved_count += 1

                return saved_count

        except Exception as e:
            logger.error(f"Error saving processing plan products: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return 0


class ProcessingPlanProcessor:
    def __init__(self, client, product_cache, task_instance):
        self.client = client
        self.product_cache = product_cache
        self.task_instance = task_instance
        self.storage = ProcessingPlanStorage(product_cache)

    async def process(self):
        """Обработка техкарт"""
        try:
            self.task_instance.update_progress(
                status=TaskStatus.RUNNING,
                message="Загрузка техкарт",
                details="Подготовка к загрузке..."
            )

            plans = self.client.get_all_processing_plans()
            structured_logger.subsection_start("Обработка техкарт")
            structured_logger.info(f"Найдено {len(plans)} техкарт")

            self.task_instance.update_progress(
                message="Обработка техкарт",
                details=f"Найдено техкарт: {len(plans)}"
            )

            @sync_to_async(thread_sensitive=True)
            def get_existing_plans():
                return {
                    plan.external_id: plan
                    for plan in ProcessingPlan.objects.all()
                }

            existing_plans = await get_existing_plans()

            plans_to_update = []
            for plan_data in plans:
                if self.task_instance.should_stop():
                    return

                plan_id = plan_data.get('id')
                if not plan_id:
                    continue

                moysklad_updated = parse_datetime(plan_data.get('updated'))
                if not moysklad_updated:
                    continue

                if timezone.is_naive(moysklad_updated):
                    moysklad_updated = timezone.make_aware(moysklad_updated)

                existing_plan = existing_plans.get(plan_id)
                if (not existing_plan or
                    not existing_plan.moysklad_updated or
                    existing_plan.moysklad_updated < moysklad_updated):
                    plans_to_update.append(plan_data)

            if plans_to_update:
                structured_logger.info(f"Найдено {len(plans_to_update)} техкарт для обновления", indent=1)
            else:
                structured_logger.info("Техкарты не требуют обновления", indent=1)

            self.task_instance.update_progress(
                message="Обработка техкарт",
                details=f"Требуют обновления: {len(plans_to_update)} техкарт"
            )

            plans_processed = 0
            total_materials = 0
            total_products = 0

            for plan_data in plans_to_update:
                if self.task_instance.should_stop():
                    return

                plan_id = plan_data['id']
                plan_details = self.client.get_processing_plan(plan_id)
                materials = self.client.get_processing_plan_materials(plan_id)
                products = self.client.get_processing_plan_products(plan_id)

                self.task_instance.update_progress(
                    details=f"Обработка техкарты {plans_processed + 1} из {len(plans_to_update)}: {plan_data.get('name', 'Без названия')}"
                )

                processing_plan = await self.storage.save_processing_plan(plan_details, moysklad_updated=plan_data.get('updated'))
                if processing_plan:
                    materials_count = await self.storage.save_processing_plan_materials(processing_plan, materials, self.client)
                    products_count = await self.storage.save_processing_plan_products(processing_plan, products, self.client)

                    total_materials += materials_count
                    total_products += products_count
                    plans_processed += 1

                if plans_processed % 10 == 0:
                    structured_logger.info(f"Обработано {plans_processed}/{len(plans_to_update)} техкарт, материалов: {total_materials}, товаров: {total_products}", indent=2)

            stats = {
                "Техкарт": plans_processed,
                "Материалов": total_materials,
                "Товаров": total_products
            }
            structured_logger.subsection_end("Обработка техкарт")
            structured_logger.stats("Результат обработки техкарт", stats)

            await self.task_instance.material_registry.load_existing_materials()

        except Exception as e:
            logger.exception("Error in process_processing_plans")
            self.task_instance.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при обработке техкарт",
                error=str(e)
            )
            raise
