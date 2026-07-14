# sync/processors/supplies.py

import asyncio
from decimal import Decimal
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from asgiref.sync import sync_to_async
from sync.models import Supply, SupplyItem, Counterparty, RawMaterial, PurchaseOrder
from sync.logger import logger, structured_logger
from sync.sync_task import TaskStatus
from sync.utils import get_group_from_pathname


class SupplyStorage:
    def __init__(self, product_cache):
        self.product_cache = product_cache

    @sync_to_async
    def save_supply_data(self, supply_data: dict, agent_data: dict, moysklad_updated: str = None) -> Supply:
        """Сохранение данных приемки"""
        try:
            with transaction.atomic():
                counterparty, _ = Counterparty.objects.get_or_create(
                    external_id=agent_data['id'],
                    defaults={'name': agent_data.get('name')}
                )

                date = timezone.datetime.fromisoformat(supply_data['moment'].replace('Z', '+00:00'))
                if timezone.is_naive(date):
                    date = timezone.make_aware(date)

                defaults = {
                    'date': date,
                    'counterparty': counterparty,
                    'number': supply_data.get('name', ''),
                    'sum': float(supply_data.get('sum', 0)) / 100
                }

                if moysklad_updated:
                    parsed_date = parse_datetime(moysklad_updated)
                    if parsed_date and timezone.is_naive(parsed_date):
                        parsed_date = timezone.make_aware(parsed_date)
                    defaults['moysklad_updated'] = parsed_date

                supply, created = Supply.objects.update_or_create(
                    external_id=supply_data['id'],
                    defaults=defaults
                )

                if not created:
                    SupplyItem.objects.filter(supply=supply).delete()

                if 'purchaseOrder' in supply_data:
                    try:
                        order_meta = supply_data['purchaseOrder']['meta']
                        order_id = order_meta['href'].split('/')[-1]

                        order = PurchaseOrder.objects.filter(
                            external_id=order_id,
                            date__lte=date
                        ).first()

                        if order:
                            supply.purchase_orders.add(order)
                            logger.info(
                                f"Supply {supply.number} ({supply.date}) linked to "
                                f"order {order.number} ({order.date})"
                            )
                        else:
                            logger.warning(
                                f"Order with external_id {order_id} not found or invalid date "
                                f"for supply {supply.number}"
                            )
                    except Exception as e:
                        logger.error(
                            f"Error linking supply {supply.number} with order: {str(e)}"
                        )

                return supply

        except Exception as e:
            logger.error(f"Error saving supply data: {str(e)}")
            return None

    @sync_to_async
    def save_supply_item(self, supply: Supply, material_data: dict, position: dict, client) -> SupplyItem:
        """Сохранение позиции приемки"""
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
                        f"Supply={supply.number}"
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

                quantity = Decimal(str(position.get('quantity', 0))).quantize(Decimal('0.01'))
                price = Decimal(str(position.get('price', 0))).quantize(Decimal('0.01')) / Decimal('100')
                total = quantity * price

                existing_item = SupplyItem.objects.filter(
                    supply=supply,
                    raw_material=raw_material
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
                        existing_item.total = total
                        existing_item.save()
                        return existing_item
                else:
                    return SupplyItem.objects.create(
                        supply=supply,
                        raw_material=raw_material,
                        quantity=quantity,
                        price=price,
                        total=total
                    )

        except Exception as e:
            logger.error(f"Error saving supply item: {str(e)}")
            return None


class SupplyProcessor:
    def __init__(self, client, product_cache, task_instance):
        self.client = client
        self.product_cache = product_cache
        self.task_instance = task_instance
        self.storage = SupplyStorage(product_cache)
        structured_logger.task_instance = task_instance

    async def process(self, time_ranges):
        """Обработка приемок"""
        structured_logger.subsection_start("Обработка приемок")
        try:
            total_ranges = len(time_ranges)

            self.task_instance.update_progress(
                message="Начало обработки приемок",
                details="Подготовка к загрузке..."
            )

            total_supplies_processed = 0
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
                    4,
                    range_progress,
                    f"Загружаем приёмки за {month_name} {year} ({i}/{total_ranges})",
                    ""
                )

                structured_logger.progress(f"Обработка приемок за период {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}", i, total_ranges)

                supplies = self.client.get_supplies_for_period(start_date, end_date)
                structured_logger.period_info(start_date, end_date, len(supplies), self.task_instance)

                @sync_to_async(thread_sensitive=True)
                def get_existing_supplies(supply_ids):
                    return {
                        s.external_id: s
                        for s in Supply.objects.filter(external_id__in=supply_ids)
                    }

                supply_ids = [s['id'] for s in supplies if 'id' in s]
                existing_supplies = await get_existing_supplies(supply_ids)

                supplies_to_update = []
                for supply_data in supplies:
                    if not supply_data.get('id'):
                        continue

                    moysklad_updated = parse_datetime(supply_data.get('updated'))
                    if not moysklad_updated:
                        continue

                    if timezone.is_naive(moysklad_updated):
                        moysklad_updated = timezone.make_aware(moysklad_updated)

                    existing_supply = existing_supplies.get(supply_data['id'])
                    if (not existing_supply or
                        not existing_supply.moysklad_updated or
                        existing_supply.moysklad_updated < moysklad_updated):
                        supplies_to_update.append(supply_data)

                if supplies_to_update:
                    structured_logger.info(f"Найдено {len(supplies_to_update)} приемок для обновления", indent=2)
                else:
                    structured_logger.info("Приемки не требуют обновления", indent=2)
                    self.task_instance._update_stage_progress(
                        4,
                        range_progress,
                        f"Приёмки за {month_name} {year} - нет обновлений ({i}/{total_ranges})",
                        ""
                    )

                for idx, supply_data in enumerate(supplies_to_update, 1):
                    if self.task_instance.should_stop():
                        return

                    supply_id = supply_data['id']
                    supply_details = self.client.get_supply_details(supply_id)
                    if not supply_details:
                        continue

                    agent_data = supply_details.get('agent', {})
                    if not agent_data:
                        continue

                    supply_number = supply_details.get('name', 'б/н')
                    supplier_name = agent_data.get('name', 'Неизвестный поставщик')
                    positions = supply_details.get('positions', {}).get('rows', [])
                    supply_date = supply_details.get('moment', '')

                    supply_date_str = ''
                    if supply_date:
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(supply_date.replace('Z', '+00:00'))
                            supply_date_str = dt.strftime('%d.%m.%Y')
                        except ValueError:
                            pass

                    self.task_instance._update_stage_progress(
                        4,
                        range_progress,
                        f"№{supply_number} ← {supplier_name}",
                        f"{supply_date_str} ({idx}/{len(supplies_to_update)})"
                    )

                    supply = await self.storage.save_supply_data(
                        supply_details,
                        agent_data,
                        moysklad_updated=supply_data.get('updated')
                    )

                    if not supply:
                        continue

                    positions_saved = 0
                    for pos_idx, position in enumerate(positions, 1):
                        if self.task_instance.should_stop():
                            return

                        material_data = position.get('assortment', {})
                        if not material_data:
                            continue

                        saved_item = await self.storage.save_supply_item(
                            supply,
                            material_data,
                            position,
                            self.client
                        )
                        if saved_item:
                            positions_saved += 1
                            total_positions_processed += 1

                    if positions_saved > 0:
                        structured_logger.success(f"Приемка №{supply_number}: сохранено {positions_saved}/{len(positions)} позиций", indent=3)
                    total_supplies_processed += 1

                    await asyncio.sleep(0.1)

            stats = {
                "Всего приемок": total_supplies_processed,
                "Всего позиций": total_positions_processed
            }
            structured_logger.subsection_end("Обработка приемок")
            structured_logger.stats("Результат обработки приемок", stats)

        except Exception as e:
            structured_logger.error(f"Ошибка при обработке приемок: {str(e)}")
            logger.exception("Error in process_supplies")
            self.task_instance.update_progress(
                status=TaskStatus.ERROR,
                message="Ошибка при обработке приемок",
                error=str(e)
            )
