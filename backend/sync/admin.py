from django.utils.safestring import mark_safe
from django.contrib import admin
from django.db.models import Q
from .models import (
    Counterparty, Product, RawMaterial, 
    ProcessingPlan, ProcessingPlanMaterial, 
    ProcessingPlanProduct, Shipment, 
    ShipmentItem, RawMaterialUsage, 
    Supply, SupplyItem, PurchaseOrder, PurchaseOrderItem
)

class BaseProductAdmin(admin.ModelAdmin):
    """Базовый класс для товаров и материалов"""
    list_display = ('name', 'article', 'code', 'group', 'uom_name')
    list_filter = ('group',)
    search_fields = ('name', 'article', 'code', 'external_id')
    ordering = ('name',)

@admin.register(Product)
class ProductAdmin(BaseProductAdmin):
    """Админка для товаров (готовой продукции)"""
    list_display = ('name', 'article', 'code', 'group', 'get_subgroup_display', 'uom_name', 'get_last_price')
    list_filter = ('group', 'subgroup')
    
    def get_subgroup_display(self, obj):
        return obj.subgroup if obj.subgroup else '-'
    get_subgroup_display.short_description = 'Подгруппа'

    def get_queryset(self, request):
        """Фильтруем только товары с подгруппой"""
        return super().get_queryset(request).filter(
            group='Товары',
            subgroup__isnull=False
        ).exclude(subgroup='')
    
    def get_last_price(self, obj):
        """Получаем последнюю цену товара из отгрузок"""
        last_shipment = obj.shipmentitem_set.order_by('-shipment__date').first()
        if last_shipment:
            return f"{last_shipment.price:,.2f} ₽"
        return '-'
    get_last_price.short_description = 'Последняя цена'

@admin.register(RawMaterial)
class ProductionMaterialAdmin(BaseProductAdmin):
    """Админка для материалов производства"""
    list_display = ('name', 'article', 'code', 'group', 'uom_name', 'get_usage_count')
    
    def get_queryset(self, request):
        """Фильтруем только материалы для производства"""
        return super().get_queryset(request).filter(group='Материалы для производства')

    def get_usage_count(self, obj):
        """Показываем в скольких товарах используется материал"""
        return obj.rawmaterialusage_set.values('shipment_item__product').distinct().count()
    get_usage_count.short_description = 'Используется в товарах'

@admin.register(ProcessingPlan)
class ProcessingPlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'created', 'updated')
    list_filter = ('created', 'updated')
    search_fields = ('name', 'external_id')
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'external_id')
        }),
        ('Временные метки', {
            'fields': ('created', 'updated'),
            'classes': ('collapse',)
        }),
    )

@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ('name', 'external_id')
    search_fields = ('name', 'external_id')

@admin.register(ProcessingPlanMaterial)
class ProcessingPlanMaterialAdmin(admin.ModelAdmin):
    list_display = ('processing_plan', 'get_material_name', 'quantity')
    list_filter = ('processing_plan', 'material')
    search_fields = ('processing_plan__name', 'material__name')

    def get_material_name(self, obj):
        return obj.material.name
    get_material_name.short_description = 'Материал'

@admin.register(ProcessingPlanProduct)
class ProcessingPlanProductAdmin(admin.ModelAdmin):
    list_display = ('processing_plan', 'get_product_name', 'quantity')
    list_filter = ('processing_plan', 'product')
    search_fields = ('processing_plan__name', 'product__name')

    def get_product_name(self, obj):
        return obj.product.name
    get_product_name.short_description = 'Продукт'

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('number', 'format_date', 'counterparty', 'get_total_sum')
    list_filter = ('counterparty', 'date')
    search_fields = ('number', 'counterparty__name')
    date_hierarchy = 'date'

    def format_date(self, obj):
        return obj.date.strftime("%d.%m.%Y %H:%M")
    format_date.short_description = 'Дата'

    def get_total_sum(self, obj):
        return f"{sum(item.total_sum for item in obj.items.all()):,.2f} ₽"
    get_total_sum.short_description = 'Сумма'

@admin.register(ShipmentItem)
class ShipmentItemAdmin(admin.ModelAdmin):
    list_display = ('get_shipment_number', 'get_shipment_date', 'get_product_name', 'quantity', 'price', 'get_total_sum')
    list_filter = ('product__group', 'product__subgroup')
    search_fields = ('shipment__number', 'product__name')

    def get_shipment_number(self, obj):
        return obj.shipment.number
    get_shipment_number.short_description = 'Номер отгрузки'
    
    def get_shipment_date(self, obj):
        return obj.shipment.date.strftime("%d.%m.%Y %H:%M")
    get_shipment_date.short_description = 'Дата'

    def get_product_name(self, obj):
        name_parts = [obj.product.name]
        if obj.product.subgroup:
            name_parts.append(f"({obj.product.subgroup})")
        return " ".join(name_parts)
    get_product_name.short_description = 'Продукт'

    def get_total_sum(self, obj):
        return f"{obj.total_sum:,.2f} ₽"
    get_total_sum.short_description = 'Сумма'

@admin.register(RawMaterialUsage)
class RawMaterialUsageAdmin(admin.ModelAdmin):
    list_display = ('get_product_name', 'get_material_name', 'quantity', 'get_shipment_info')
    list_filter = ('raw_material__group', 'shipment_item__product__group')
    search_fields = ('raw_material__name', 'shipment_item__product__name')

    def get_product_name(self, obj):
        return obj.shipment_item.product.name
    get_product_name.short_description = 'Продукт'

    def get_material_name(self, obj):
        return obj.raw_material.name
    get_material_name.short_description = 'Материал'

    def get_shipment_info(self, obj):
        return f"Отгрузка №{obj.shipment_item.shipment.number}"
    get_shipment_info.short_description = 'Отгрузка'

@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = ('number', 'date', 'counterparty', 'sum')
    list_filter = ('counterparty', 'date')
    search_fields = ('number', 'counterparty__name')
    date_hierarchy = 'date'

@admin.register(SupplyItem)
class SupplyItemAdmin(admin.ModelAdmin):
    list_display = ('get_supply_number', 'get_supply_date', 'get_material_name', 'quantity', 'price', 'total')
    list_filter = ('raw_material__group',)
    search_fields = ('supply__number', 'raw_material__name')

    def get_supply_number(self, obj):
        return obj.supply.number
    get_supply_number.short_description = 'Номер приемки'
    
    def get_supply_date(self, obj):
        return obj.supply.date.strftime("%d.%m.%Y %H:%M")
    get_supply_date.short_description = 'Дата'

    def get_material_name(self, obj):
        return obj.raw_material.name
    get_material_name.short_description = 'Материал'

@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        'number',
        'get_formatted_date',
        'counterparty',
        'status',
        'sum',
        'get_supply_info',
        'get_order_status',
        'get_lead_time'
    )
    list_display_links = ('number',)
    search_fields = ('number', 'counterparty__name', 'external_id')
    list_filter = (
        'status',
        ('date', admin.DateFieldListFilter),
        'counterparty',
    )
    date_hierarchy = 'date'
    ordering = ('-date',)

    def get_formatted_date(self, obj):
        return obj.date.strftime("%d.%m.%Y %H:%M")
    get_formatted_date.admin_order_field = 'date'
    get_formatted_date.short_description = 'Дата'

    def get_supply_info(self, obj):
        supplies = obj.supplies.all()
        if supplies:
            supply_list = [f"№{s.number} от {s.date.strftime('%d.%m.%Y')}" for s in supplies]
            return mark_safe("<br>".join(supply_list))
        return '-'
    get_supply_info.short_description = 'Приемки'
    get_supply_info.allow_tags = True

    def get_order_status(self, obj):
        """Статус выполнения заказа"""
        items = obj.items.all()
        if not items:
            return '-'

        total_ordered = sum(item.quantity for item in items)
        total_shipped = sum(item.shipped_quantity for item in items)
        total_waiting = sum(item.waiting_quantity for item in items)
        remaining = total_ordered - total_shipped - total_waiting

        status_parts = []
        if total_shipped > 0:
            status_parts.append(f"Принято: {total_shipped:g}")
        if total_waiting > 0:
            status_parts.append(f"В пути: {total_waiting:g}")
        if remaining > 0:
            status_parts.append(f"Ожидается: {remaining:g}")
            
        if not status_parts:
            return '-'
        
        return mark_safe("<br>".join(status_parts))
    get_order_status.allow_tags = True    
    get_order_status.short_description = 'Статус позиций'

    def get_lead_time(self, obj):
        try:
            supply = obj.supplies.order_by('date').first()
            if supply and obj.date:
                lead_time = (supply.date - obj.date).days
                return f"{lead_time} дн."
        except Exception:
            pass
        return '-'
    get_lead_time.short_description = 'Lead Time'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'supplies',
            'items'
        )
    

@admin.register(PurchaseOrderItem)
class PurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'get_order_number', 
        'get_order_date', 
        'get_material_name',
        'quantity',
        'shipped_quantity',
        'waiting_quantity',
        'price', 
        'total'
    )
    list_filter = ('raw_material__group', 'purchase_order__status')
    search_fields = ('purchase_order__number', 'raw_material__name')

    def get_order_number(self, obj):
        return obj.purchase_order.number
    get_order_number.short_description = 'Номер заказа'
    
    def get_order_date(self, obj):
        return obj.purchase_order.date.strftime("%d.%m.%Y %H:%M")
    get_order_date.short_description = 'Дата'

    def get_material_name(self, obj):
        return obj.raw_material.name
    get_material_name.short_description = 'Материал'