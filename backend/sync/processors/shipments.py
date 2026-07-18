# sync/processors/shipments.py

import asyncio
from decimal import Decimal
from django.db import DatabaseError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from sync.models import (
    Shipment, ShipmentItem, Counterparty,
    Product, RawMaterialUsage
)
from sync.logger import logger, structured_logger
from sync.sync_task import TaskStatus
from sync.cache import ProductDetailsFetchError
from sync.utils import get_group_from_pathname


class ShipmentStorage:
    def __init__(self, product_cache, material_registry):
        self.product_cache = product_cache
        self.material_registry = material_registry

    @sync_to_async
    def save_shipment_data(self, shipment_data: dict, agent_data: dict, moysklad_updated: str = None) -> Shipment:
        """Сохранение данных отгрузки"""
        try:
            with transaction.atomic():
                counterparty, _ = Counterparty.objects.get_or_create(
                    external_id=agent_data['id'],
                    defaults={'name': agent_data.get('name')}
                )

                date = timezone.datetime.fromisoformat(shipment_data['moment'].replace('Z', '+00:00'))
                if timezone.is_naive(date):
                    date = timezone.make_aware(date)

                defaults = {
                    'date': date,
                    'counterparty': counterparty,
                    'number': shipment_data.get('name', '')
                }

                if moysklad_updated:
                    parsed_date = parse_datetime(moysklad_updated)
                    if parsed_date and timezone.is_naive(parsed_date):
                        parsed_date = timezone.make_aware(parsed_date)
                    defaults['moysklad_updated'] = parsed_date

                shipment, created = Shipment.objects.update_or_create(
                    external_id=shipment_data['id'],
                    defaults=defaults
                )

                return shipment
        except Exception as e:
            logger.error(f"Error saving shipment: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return None

    @sync_to_async
    def save_shipment_item(self, shipment: Shipment, product_data: dict, position: dict, client) -> ShipmentItem:
        """Сохранение позиции отгрузки"""
        try:
            with transaction.atomic():
                if product_data.get('name') == 'Доставка':
                    structured_logger.info(f"    Пропущена доставка для отгрузки №{shipment.number}")
                    return None

                product_details = self.product_cache.get_product_details(
                    client,
                    product_data['id'],
                    is_material=False
                )

                if not product_details:
                    logger.warning(
                        f"No details found for product: ID={product_data['id']}, "
                        f"Name={product_data.get('name', 'Unknown')}, "
                        f"Shipment={shipment.number}"
                    )
                    return None

                path_name = product_details.get('pathName', '')
                path_parts = path_name.split('/') if path_name else []
                group = get_group_from_pathname(path_name)
                subgroup = path_parts[1].strip() if len(path_parts) > 1 else None

                product, _ = Product.objects.update_or_create(
                    external_id=product_data['id'],
                    defaults={
                        'name': product_data.get('name'),
                        'uom_name': product_details.get('uom', {}).get('name'),
                        'group': group,
                        'subgroup': subgroup,
                        'article': product_details.get('article'),
                        'code': product_details.get('code'),
                        'description': product_details.get('description')
                    }
                )

                quantity = Decimal(str(position.get('quantity', 0))).quantize(Decimal('0.01'))
                price = Decimal(str(position.get('price', 0))).quantize(Decimal('0.01')) / Decimal('100')

                existing_item = ShipmentItem.objects.filter(
                    shipment=shipment,
                    product=product
                ).first()

                if existing_item:
                    existing_quantity = Decimal(str(existing_item.quantity)).quantize(Decimal('0.01'))
                    existing_price = Decimal(str(existing_item.price)).quantize(Decimal('0.01'))

                    if (
                        abs(existing_quantity - quantity) <= Decimal('0.01') and
                        abs(existing_price - price) <= Decimal('0.01')
                    ):
                        return existing_item
                    else:
                        existing_item.quantity = quantity
                        existing_item.price = price
                        existing_item.save()

                        RawMaterialUsage.objects.filter(shipment_item=existing_item).delete()
                        shipment_item = existing_item
                else:
                    shipment_item = ShipmentItem.objects.create(
                        shipment=shipment,
                        product=product,
                        quantity=quantity,
                        price=price
                    )

                materials = self.material_registry.get_materials_for_product(product.external_id)
                for material_data in materials:
                    material = material_data['material']
                    material_quantity = Decimal(str(material_data['quantity'])) * quantity

                    RawMaterialUsage.objects.create(
                        shipment_item=shipment_item,
                        raw_material=material,
                        quantity=material_quantity
                    )

                return shipment_item

        except Exception as e:
            logger.error(f"Error saving shipment item: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return None

    @sync_to_async
    def cleanup_orphaned_items(self, shipment: Shipment, valid_product_ids: list) -> int:
        """Удаление позиций отгрузки, которые больше не присутствуют в данных из МойСклад."""
        try:
            with transaction.atomic():
                orphaned_items = ShipmentItem.objects.filter(
                    shipment=shipment
                ).exclude(
                    product__external_id__in=valid_product_ids
                )

                count = orphaned_items.count()
                if count > 0:
                    RawMaterialUsage.objects.filter(shipment_item__in=orphaned_items).delete()
                    orphaned_items.delete()
                    logger.info(f"Удалено {count} устаревших позиций из отгрузки {shipment.number}")

                return count
        except Exception as e:
            logger.error(f"Error cleaning up orphaned items: {str(e)}")
            if isinstance(e, DatabaseError):
                raise
            return 0


class ShipmentProcessor:
    def __init__(self, client, product_cache, material_registry, task_instance):
        self.client = client
        self.product_cache = product_cache
        self.material_registry = material_registry
        self.task_instance = task_instance
        self.storage = ShipmentStorage(product_cache, material_registry)
        structured_logger.task_instance = task_instance

    async def process(self, time_ranges):
        """Обработка отгрузок"""
        structured_logger.subsection_start("Обработка отгрузок")
        try:
            await self.material_registry.load_existing_materials()

            total_ranges = len(time_ranges)

            self.task_instance.update_progress(
                message="Начало обработки отгрузок",
                details="Подготовка к загрузке..."
            )

            total_shipments_processed = 0
            total_positions_processed = 0

            for i, (start_date, end_date) in enumerate(time_ranges, 1):
                if self.task_instance.should_stop():
                    return

                range_progress = i / total_ranges if total_ranges > 0 else 1.0
                months_ru = [
                    'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
                    'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
                ]
                month_name = months_ru[start_date.month - 1]
                year = start_date.year

                self.task_instance._update_stage_progress(
                    5,
                    range_progress,
                    f"Загружаем отгрузки за {month_name} {year} ({i}/{total_ranges})",
                    ""
                )

                structured_logger.progress(f"Обработка отгрузок за период {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}", i, total_ranges)

                shipments = self.client.get_shipments_for_period(start_date, end_date)
                structured_logger.period_info(start_date, end_date, len(shipments), self.task_instance)

                @sync_to_async(thread_sensitive=True)
                def get_existing_shipments(shipment_ids):
                    from django.db.models import Count
                    return {
                        s.external_id: s
                        for s in Shipment.objects.filter(external_id__in=shipment_ids)
                            .annotate(items_count=Count('items'))
                    }

                shipment_ids = [s['id'] for s in shipments if 'id' in s]
                existing_shipments = await get_existing_shipments(shipment_ids)

                @sync_to_async(thread_sensitive=True)
                def delete_removed_shipments(api_ids, period_start, period_end):
                    deleted = Shipment.objects.filter(
                        date__gte=period_start,
                        date__lt=period_end,
                    ).exclude(external_id__in=api_ids).delete()
                    return deleted[0]

                deleted_count = await delete_removed_shipments(shipment_ids, start_date, end_date)
                if deleted_count:
                    structured_logger.info(f"Удалено {deleted_count} отгрузок (удалены в МойСклад)", indent=2)

                shipments_to_update = []
                for shipment_data in shipments:
                    if not shipment_data.get('id'):
                        continue

                    moysklad_updated = parse_datetime(shipment_data.get('updated'))
                    if not moysklad_updated:
                        continue

                    if timezone.is_naive(moysklad_updated):
                        moysklad_updated = timezone.make_aware(moysklad_updated)

                    existing_shipment = existing_shipments.get(shipment_data['id'])
                    has_empty_items = existing_shipment and existing_shipment.items_count == 0
                    if (not existing_shipment or
                        has_empty_items or
                        not existing_shipment.moysklad_updated or
                        existing_shipment.moysklad_updated < moysklad_updated):
                        shipments_to_update.append(shipment_data)

                if shipments_to_update:
                    structured_logger.info(f"Найдено {len(shipments_to_update)} отгрузок для обновления", indent=2)
                else:
                    structured_logger.info("Отгрузки не требуют обновления", indent=2)
                    self.task_instance._update_stage_progress(
                        5,
                        range_progress,
                        f"Отгрузки за {month_name} {year} - нет обновлений ({i}/{total_ranges})",
                        ""
                    )

                batch_size = 5
                batches = [shipments_to_update[j:j + batch_size] for j in range(0, len(shipments_to_update), batch_size)]

                for batch_idx, batch in enumerate(batches, 1):
                    if self.task_instance.should_stop():
                        return

                    semaphore = asyncio.Semaphore(batch_size)

                    async def process_single_shipment(shipment_data, idx_in_batch):
                        async with semaphore:
                            shipment_id = shipment_data['id']

                            @sync_to_async(thread_sensitive=True)
                            def get_details():
                                return self.client.get_shipment_details(shipment_id)

                            shipment_details = await get_details()
                            if not shipment_details:
                                return 0

                            agent_data = shipment_details.get('agent', {})
                            if not agent_data:
                                return 0

                            shipment_number = shipment_details.get('name', 'б/н')
                            agent_name = agent_data.get('name', 'Неизвестный контрагент')
                            positions = shipment_details.get('positions', {}).get('rows', [])
                            shipment_date = shipment_details.get('moment', '')

                            shipment_date_str = ''
                            if shipment_date:
                                try:
                                    from datetime import datetime
                                    dt = datetime.fromisoformat(shipment_date.replace('Z', '+00:00'))
                                    shipment_date_str = dt.strftime('%d.%m.%Y')
                                except ValueError:
                                    pass

                            global_idx = (batch_idx - 1) * batch_size + idx_in_batch + 1
                            if len(shipments_to_update) > 0:
                                period_progress = global_idx / len(shipments_to_update)
                                base_range_progress = (i - 1) / total_ranges
                                range_weight = 1.0 / total_ranges
                                total_stage_progress = base_range_progress + (period_progress * range_weight)

                                self.task_instance._update_stage_progress(
                                    5,
                                    total_stage_progress,
                                    f"№{shipment_number} → {agent_name}",
                                    f"{shipment_date_str} ({global_idx}/{len(shipments_to_update)})"
                                )

                            shipment = await self.storage.save_shipment_data(
                                shipment_details,
                                agent_data,
                                moysklad_updated=shipment_data.get('updated')
                            )

                            if not shipment:
                                return 0

                            positions_saved = 0
                            if positions:
                                for position in positions:
                                    if self.task_instance.should_stop():
                                        return positions_saved

                                    assortment = position.get('assortment', {})
                                    if assortment:
                                        saved_item = await self.storage.save_shipment_item(
                                            shipment,
                                            assortment,
                                            position,
                                            self.client
                                        )
                                        if saved_item:
                                            positions_saved += 1

                            if positions_saved > 0:
                                structured_logger.success(f"Отгрузка №{shipment_number}: сохранено {positions_saved}/{len(positions)} позиций", indent=3)

                            return positions_saved

                    tasks = [
                        process_single_shipment(shipment_data, idx)
                        for idx, shipment_data in enumerate(batch)
                    ]

                    results = await asyncio.gather(*tasks)

                    for result in results:
                        total_positions_processed += result
                        total_shipments_processed += 1

                    await asyncio.sleep(0.4)

                self.task_instance.update_progress(
                    message=(
                        f"Период {i}/{total_ranges} завершен. "
                        f"Обработано отгрузок: {total_shipments_processed}, "
                        f"позиций: {total_positions_processed}"
                    )
                )

            stats = {
                "Всего отгрузок": total_shipments_processed,
                "Всего позиций": total_positions_processed
            }
            structured_logger.subsection_end("Обработка отгрузок")
            structured_logger.stats("Результат обработки отгрузок", stats)

        except Exception as e:
            structured_logger.error(f"Ошибка при обработке отгрузок: {str(e)}")
            logger.exception("Error in process_shipments")
            self.task_instance.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при обработке отгрузок",
                error=str(e)
            )
            raise
