# sync/processors/purchases.py

import asyncio
from decimal import Decimal
from django.db import DatabaseError, transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from sync.models import PurchaseOrder, PurchaseOrderItem, Counterparty, RawMaterial, Supply
from sync.logger import logger, structured_logger
from sync.sync_task import TaskStatus
from sync.cache import ProductDetailsFetchError
from sync.utils import get_group_from_pathname


class PurchaseOrderStorage:
    """Хранилище для заказов поставщиков"""

    def __init__(self, product_cache):
        self.product_cache = product_cache

    @sync_to_async
    def save_purchase_order_data(self, order_data: dict, agent_data: dict, moysklad_updated: str = None) -> PurchaseOrder:
        """Сохранение данных заказа"""
        try:
            with transaction.atomic():
                counterparty, _ = Counterparty.objects.get_or_create(
                    external_id=agent_data['id'],
                    defaults={'name': agent_data.get('name')}
                )

                date = timezone.datetime.fromisoformat(order_data['moment'].replace('Z', '+00:00'))
                if timezone.is_naive(date):
                    date = timezone.make_aware(date)

                created = timezone.datetime.fromisoformat(order_data['created'].replace('Z', '+00:00'))
                if timezone.is_naive(created):
                    created = timezone.make_aware(created)

                state_name = order_data.get('state', {}).get('name')

                defaults = {
                    'date': date,
                    'created': created,
                    'counterparty': counterparty,
                    'number': order_data.get('name', ''),
                    'status': state_name,
                    'sum': float(order_data.get('sum', 0)) / 100
                }

                if moysklad_updated:
                    parsed_date = parse_datetime(moysklad_updated)
                    if parsed_date and timezone.is_naive(parsed_date):
                        parsed_date = timezone.make_aware(parsed_date)
                    defaults['moysklad_updated'] = parsed_date

                purchase_order, created = PurchaseOrder.objects.update_or_create(
                    external_id=order_data['id'],
                    defaults=defaults
                )

                if not created:
                    purchase_order.items.all().delete()

                if 'supplies' in order_data:
                    for supply_link in order_data['supplies']:
                        try:
                            supply_href = supply_link['meta']['href']
                            supply_id = supply_href.split('/')[-1]

                            supply = Supply.objects.filter(
                                external_id=supply_id,
                                date__gte=date
                            ).first()

                            if supply:
                                purchase_order.supplies.add(supply)
                                logger.info(
                                    f"Order {purchase_order.number} ({purchase_order.date}) "
                                    f"linked to supply {supply.number} ({supply.date})"
                                )
                            else:
                                logger.warning(
                                    f"Supply with external_id {supply_id} not found or invalid date "
                                    f"for order {purchase_order.number}"
                                )
                        except Exception as e:
                            if isinstance(e, DatabaseError):
                                raise
                            logger.error(
                                f"Error linking order {purchase_order.number} with supply: {str(e)}"
                            )

                return purchase_order

        except Exception as e:
            logger.error(f"Error saving purchase order data: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return None

    @sync_to_async
    def save_purchase_order_item(self, purchase_order: PurchaseOrder, material_data: dict, position: dict, client) -> PurchaseOrderItem:
        """Сохранение позиции заказа"""
        try:
            with transaction.atomic():
                material_details = self.product_cache.get_product_details(
                    client,
                    material_data['id'],
                    is_material=True
                )

                if not material_details:
                    logger.warning(
                        f"No details found for material: ID={material_data['id']}, "
                        f"Name={material_data.get('name', 'Unknown')}, "
                        f"Order={purchase_order.number}"
                    )
                    return None

                path_name = material_details.get('pathName', '')
                group = get_group_from_pathname(path_name)

                raw_material, _ = RawMaterial.objects.update_or_create(
                    external_id=material_data['id'],
                    defaults={
                        'name': material_data.get('name'),
                        'uom_name': material_details.get('uom', {}).get('name'),
                        'uom_description': material_details.get('uom', {}).get('description'),
                        'group': group,
                        'article': material_details.get('article'),
                        'code': material_details.get('code'),
                        'description': material_details.get('description')
                    }
                )

                quantity = Decimal(str(position.get('quantity', 0))).quantize(Decimal('0.001'))
                price = Decimal(str(position.get('price', 0))).quantize(Decimal('0.01')) / Decimal('100')
                total = quantity * price
                shipped = Decimal(str(position.get('shipped', 0))).quantize(Decimal('0.001'))
                waiting = Decimal(str(position.get('inTransit', 0))).quantize(Decimal('0.001'))

                return PurchaseOrderItem.objects.create(
                    purchase_order=purchase_order,
                    raw_material=raw_material,
                    quantity=quantity,
                    price=price,
                    total=total,
                    shipped_quantity=shipped,
                    waiting_quantity=waiting
                )

        except Exception as e:
            logger.error(f"Error saving purchase order item: {str(e)}")
            if isinstance(e, (DatabaseError, ProductDetailsFetchError)):
                raise
            return None


class PurchaseOrderProcessor:
    """Обработчик заказов поставщикам"""

    def __init__(self, client, product_cache, task_instance):
        self.client = client
        self.product_cache = product_cache
        self.task_instance = task_instance
        self.storage = PurchaseOrderStorage(product_cache)
        structured_logger.task_instance = task_instance

    async def process(self, time_ranges):
        """Обработка заказов поставщикам"""
        structured_logger.subsection_start("Обработка заказов поставщикам")
        try:
            total_ranges = len(time_ranges)

            self.task_instance.update_progress(
                message="Начало обработки заказов поставщикам",
                details="Подготовка к загрузке..."
            )

            total_orders_processed = 0
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
                    3,
                    range_progress,
                    f"Загружаем заказы поставщикам за {month_name} {year} ({i}/{total_ranges})",
                    ""
                )

                structured_logger.progress(f"Обработка заказов за период {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}", i, total_ranges)

                orders = self.client.get_purchase_orders_for_period(start_date, end_date)
                structured_logger.period_info(start_date, end_date, len(orders), self.task_instance)

                @sync_to_async(thread_sensitive=True)
                def get_existing_orders(order_ids):
                    return {
                        o.external_id: o
                        for o in PurchaseOrder.objects.filter(external_id__in=order_ids)
                    }

                order_ids = [o['id'] for o in orders if 'id' in o]
                existing_orders = await get_existing_orders(order_ids)

                orders_to_update = []
                for order_data in orders:
                    if not order_data.get('id'):
                        continue

                    moysklad_updated = parse_datetime(order_data.get('updated'))
                    if not moysklad_updated:
                        continue

                    if timezone.is_naive(moysklad_updated):
                        moysklad_updated = timezone.make_aware(moysklad_updated)

                    existing_order = existing_orders.get(order_data['id'])
                    if (not existing_order or
                        not existing_order.moysklad_updated or
                        existing_order.moysklad_updated < moysklad_updated):
                        orders_to_update.append(order_data)

                if orders_to_update:
                    structured_logger.info(f"Найдено {len(orders_to_update)} заказов для обновления", indent=2)
                else:
                    structured_logger.info("Заказы не требуют обновления", indent=2)
                    self.task_instance._update_stage_progress(
                        3,
                        range_progress,
                        f"Заказы поставщикам за {month_name} {year} - нет обновлений ({i}/{total_ranges})",
                        ""
                    )

                material_ids = set()
                for order_data in orders_to_update:
                    order_details = self.client.get_purchase_order_details(order_data['id'])
                    if not order_details:
                        continue

                    for position in order_details.get('positions', {}).get('rows', []):
                        assortment = position.get('assortment', {})
                        if assortment and assortment.get('id'):
                            material_ids.add(assortment['id'])

                if material_ids and self.product_cache:
                    structured_logger.info(f"Предзагрузка {len(material_ids)} материалов", indent=2)
                    self.product_cache.bulk_prefetch(self.client, material_ids, is_material=True)

                for idx, order_data in enumerate(orders_to_update, 1):
                    if self.task_instance.should_stop():
                        return

                    order_id = order_data['id']
                    order_details = self.client.get_purchase_order_details(order_id)
                    if not order_details:
                        continue

                    agent_data = order_details.get('agent', {})
                    if not agent_data:
                        continue

                    order_number = order_details.get('name', 'б/н')
                    agent_name = agent_data.get('name', 'Неизвестный поставщик')
                    state_name = order_details.get('state', {}).get('name', 'Новый')
                    positions = order_details.get('positions', {}).get('rows', [])
                    order_date = order_details.get('moment', '')

                    order_date_str = ''
                    if order_date:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(order_date.replace('Z', '+00:00'))
                            order_date_str = dt.strftime('%d.%m.%Y')
                        except ValueError:
                            pass

                    self.task_instance._update_stage_progress(
                        3,
                        range_progress,
                        f"№{order_number} → {agent_name}",
                        f"{order_date_str} ({idx}/{len(orders_to_update)})"
                    )

                    purchase_order = await self.storage.save_purchase_order_data(
                        order_details,
                        agent_data,
                        moysklad_updated=order_data.get('updated')
                    )

                    if not purchase_order:
                        continue

                    positions_saved = 0
                    if positions:
                        for position in positions:
                            if self.task_instance.should_stop():
                                return

                            assortment = position.get('assortment', {})
                            if assortment:
                                saved_item = await self.storage.save_purchase_order_item(
                                    purchase_order,
                                    assortment,
                                    position,
                                    self.client
                                )
                                if saved_item:
                                    positions_saved += 1
                                    total_positions_processed += 1

                    if positions_saved > 0:
                        structured_logger.success(f"Заказ №{order_number}: сохранено {positions_saved}/{len(positions)} позиций", indent=3, to_ui=True)
                    total_orders_processed += 1

                    await asyncio.sleep(0.1)

            stats = {
                "Всего заказов": total_orders_processed,
                "Всего позиций": total_positions_processed
            }
            structured_logger.subsection_end("Обработка заказов поставщикам")
            structured_logger.stats("Результат обработки заказов", stats)

        except Exception as e:
            structured_logger.error(f"Ошибка при обработке заказов поставщикам: {str(e)}")
            logger.exception("Error in process_purchase_orders")
            self.task_instance.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при обработке заказов поставщикам",
                error=str(e)
            )
            raise
