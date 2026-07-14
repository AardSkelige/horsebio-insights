# api/views/shipments.py
from sync.sync_task import TaskManager
from django.http import JsonResponse
from django.utils import timezone
from django.core.cache import cache

from core.models import (
    Shipment,
    Supply
)
from api.exceptions import DataProcessingError

import logging
logger = logging.getLogger(__name__)

def shipment_data(request):
    """API endpoint для получения данных по отгрузкам"""
    try:
        # Получаем базовый набор отгрузок с prefetch для избежания N+1 queries
        shipments = Shipment.objects.filter(
            items__product__group='Товары',
            items__product__subgroup__isnull=False
        ).exclude(
            items__product__subgroup=''
        ).select_related(
            'counterparty'
        ).prefetch_related(
            'items__product',
            'items__raw_material_usages__raw_material'
        ).distinct()

        formatted_data = []

        # Все связанные данные уже загружены через prefetch_related
        for shipment in shipments:
            # Обработка позиций отгрузки (уже в памяти благодаря prefetch)
            for item in shipment.items.all():
                if item.product.group == 'Товары' and item.product.subgroup:
                    formatted_item = {
                        'counterparty_name': shipment.counterparty.name,
                        'counterparty_id': shipment.counterparty.id,
                        'shipment_id': shipment.id,
                        'shipment_number': shipment.number,
                        'shipment_date': timezone.localtime(shipment.date).isoformat(),
                        'product_name': item.product.name,
                        'product_id': item.product.id,
                        'product_group': item.product.group,
                        'product_subgroup': item.product.subgroup,
                        'quantity': float(item.quantity),
                        'price': float(item.price),
                        'total_sum': float(item.total_sum),
                        'materials': [
                            {
                                'name': usage.raw_material.name,
                                'quantity': float(usage.quantity),
                                'uom': usage.raw_material.uom_name
                            }
                            for usage in item.raw_material_usages.all()
                        ]
                    }
                    formatted_data.append(formatted_item)

        return JsonResponse({
            'status': 'success',
            'data': formatted_data
        })

    except Exception as e:
        logger.error(f"Error in shipment_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных по отгрузкам")

def get_stats(request):
    """API endpoint для получения общей статистики"""
    try:
        from datetime import datetime, date
        import calendar
        
        # Получаем первый день текущего месяца
        today = timezone.now()
        first_day_of_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Получаем названия месяцев на русском
        month_names = [
            'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ]

        # Базовые запросы для отгрузок и приемок
        shipments_base = Shipment.objects.filter(
            items__product__group='Товары',
            items__product__subgroup__isnull=False
        ).exclude(
            items__product__subgroup=''
        )
        
        supplies_base = Supply.objects.all()

        # Получаем времена последних обновлений из кэша
        last_manual_update = cache.get('last_manual_update')
        last_auto_update = cache.get('last_auto_sync_update')
        last_general_update = cache.get('last_successful_update')
        
        # Fallback логика: если нет ручного обновления, ищем время последней отгрузки/приемки
        if not last_manual_update:
            try:
                last_shipment = Shipment.objects.order_by('-moysklad_updated').first()
                last_supply = Supply.objects.order_by('-moysklad_updated').first()
                
                fallback_time = None
                if last_shipment and last_supply:
                    if last_shipment.moysklad_updated and last_supply.moysklad_updated:
                        fallback_time = max(last_shipment.moysklad_updated, last_supply.moysklad_updated)
                    elif last_shipment.moysklad_updated:
                        fallback_time = last_shipment.moysklad_updated
                    elif last_supply.moysklad_updated:
                        fallback_time = last_supply.moysklad_updated
                elif last_shipment and last_shipment.moysklad_updated:
                    fallback_time = last_shipment.moysklad_updated
                elif last_supply and last_supply.moysklad_updated:
                    fallback_time = last_supply.moysklad_updated
                
                # Используем fallback как ручное обновление
                if fallback_time:
                    last_manual_update = fallback_time
            except Exception as e:
                # В случае ошибки устанавливаем None
                last_manual_update = None

        # Вычисляем границы для последних 3 месяцев
        last_3_months_stats = []
        
        for i in range(1, 4):  # 1, 2, 3 месяца назад
            # Получаем дату начала месяца i месяцев назад
            if today.month - i <= 0:
                target_year = today.year - 1
                target_month = 12 + (today.month - i)
            else:
                target_year = today.year
                target_month = today.month - i
            
            # Первый день месяца
            month_start = timezone.datetime(target_year, target_month, 1, tzinfo=today.tzinfo)
            
            # Последний день месяца
            last_day = calendar.monthrange(target_year, target_month)[1]
            month_end = timezone.datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=today.tzinfo)
            
            # Подсчитываем статистику для этого месяца
            shipments_count = shipments_base.filter(
                date__gte=month_start,
                date__lte=month_end
            ).distinct().count()
            
            supplies_count = supplies_base.filter(
                date__gte=month_start,
                date__lte=month_end
            ).distinct().count()
            
            last_3_months_stats.append({
                'month': month_names[target_month - 1],
                'year': target_year,
                'shipments': shipments_count,
                'supplies': supplies_count
            })

        # Получаем последние отгрузки и приемки для карточек
        last_3_shipments = []
        last_6_shipments = []
        last_10_shipments = []
        last_3_supplies = []
        last_6_supplies = []
        last_10_supplies = []
        
        try:
            # Последние 10 отгрузок
            recent_shipments = shipments_base.order_by('-date').distinct()[:10]
            for shipment in recent_shipments:
                shipment_data = {
                    'number': shipment.number,
                    'date': timezone.localtime(shipment.date).isoformat() if shipment.date else None,
                    'external_id': shipment.external_id
                }
                last_10_shipments.append(shipment_data)
            
            # Для обратной совместимости
            last_6_shipments = last_10_shipments[:6]
            last_3_shipments = last_10_shipments[:3]
            
            # Последние 10 приемок
            recent_supplies = supplies_base.order_by('-date')[:10]
            for supply in recent_supplies:
                supply_data = {
                    'number': supply.number,
                    'date': supply.date.isoformat() if supply.date else None,
                    'external_id': supply.external_id
                }
                last_10_supplies.append(supply_data)
            
            # Для обратной совместимости
            last_6_supplies = last_10_supplies[:6]
            last_3_supplies = last_10_supplies[:3]
        except Exception as e:
            # В случае ошибки возвращаем пустые списки
            last_3_shipments = []
            last_6_shipments = []
            last_10_shipments = []
            last_3_supplies = []
            last_6_supplies = []
            last_10_supplies = []

        stats = {
            'shipments_count': shipments_base.distinct().count(),
            'shipments_current_month': shipments_base.filter(
                date__gte=first_day_of_month
            ).distinct().count(),
            
            'supplies_count': supplies_base.distinct().count(),
            'supplies_current_month': supplies_base.filter(
                date__gte=first_day_of_month
            ).distinct().count(),
            
            'last_3_months': last_3_months_stats,
            
            # Последние отгрузки и приемки для карточек
            'last_3_shipments': last_3_shipments,
            'last_6_shipments': last_6_shipments,
            'last_10_shipments': last_10_shipments,
            'last_3_supplies': last_3_supplies,
            'last_6_supplies': last_6_supplies,
            'last_10_supplies': last_10_supplies,
            
            # Информация об обновлениях
            'last_manual_update': timezone.localtime(last_manual_update).strftime("%d.%m.%Y %H:%M") if last_manual_update else None,
            'last_auto_update': timezone.localtime(last_auto_update).strftime("%d.%m.%Y %H:%M") if last_auto_update else None,
            
            # Определяем какое обновление было последним
            'latest_update_type': None,
            'latest_update_time': None
        }
        
        # Определяем какое обновление было самым последним
        updates = []
        if last_manual_update:
            updates.append(('manual', last_manual_update))
        if last_auto_update:
            updates.append(('auto', last_auto_update))
            
        if updates:
            latest_type, latest_time = max(updates, key=lambda x: x[1])
            stats['latest_update_type'] = latest_type
            stats['latest_update_time'] = timezone.localtime(latest_time).strftime("%d.%m.%Y %H:%M")
        
        return JsonResponse({
            'status': 'success',
            'stats': stats
        })
    except Exception as e:
        logger.error(f"Error in get_stats: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения статистики")


def get_latest_data(request):
    """API endpoint для получения последних отгрузок и приемок"""
    try:
        # Получаем последние 5 отгрузок
        latest_shipments = Shipment.objects.select_related(
            'counterparty'
        ).prefetch_related(
            'items'
        ).filter(
            items__product__group='Товары',
            items__product__subgroup__isnull=False
        ).exclude(
            items__product__subgroup=''
        ).order_by(
            '-date'
        ).distinct()[:5]

        # Получаем последние 5 приемок
        latest_supplies = Supply.objects.select_related(
            'counterparty'
        ).prefetch_related(
            'items'
        ).order_by('-date')[:5]

        # Форматируем данные отгрузок
        shipments_data = [{
            'number': shipment.number,
            'date': timezone.localtime(shipment.date).isoformat(),
            'total_sum': sum(item.total_sum for item in shipment.items.all()),
            'items_count': shipment.items.count()
        } for shipment in latest_shipments]

        # Форматируем данные приемок
        supplies_data = [{
            'number': supply.number,
            'date': supply.date.isoformat(),
            'total_sum': float(supply.sum),
            'items_count': supply.items.count()
        } for supply in latest_supplies]

        return JsonResponse({
            'status': 'success',
            'data': {
                'shipments': shipments_data,
                'supplies': supplies_data
            }
        })
    except Exception as e:
        logger.error(f"Error in get_latest_data: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения последних данных")
