from django.contrib import admin
from django.utils import timezone

from .models import (
    OzonDeliveryQuote, OzonOAuthToken, OzonPickupPoint, OzonPosting, OzonProduct,
    OzonReturn,
)


@admin.register(OzonOAuthToken)
class OzonOAuthTokenAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'has_refresh_token', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(boolean=True, description='refresh_token')
    def has_refresh_token(self, obj):
        return bool(obj.refresh_token)


@admin.register(OzonProduct)
class OzonProductAdmin(admin.ModelAdmin):
    list_display = ('offer_id', 'sku', 'has_fbs_stocks', 'archived', 'synced_at')
    list_filter = ('has_fbs_stocks', 'has_fbo_stocks', 'archived')
    search_fields = ('offer_id', 'sku')
    readonly_fields = ('synced_at',)


@admin.register(OzonPickupPoint)
class OzonPickupPointAdmin(admin.ModelAdmin):
    list_display = ('map_point_id', 'address', 'latitude', 'longitude', 'details_synced_at')
    search_fields = ('map_point_id', 'address', 'name')
    readonly_fields = ('synced_at', 'details_synced_at', 'details')


@admin.register(OzonDeliveryQuote)
class OzonDeliveryQuoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'phone', 'status', 'delivery_cost', 'site_order_id',
                    'order_number', 'created_at')
    list_filter = ('status',)
    search_fields = ('id', 'phone', 'site_order_id', 'order_number')
    readonly_fields = ('created_at', 'ordered_at', 'checkout_response')


@admin.register(OzonPosting)
class OzonPostingAdmin(admin.ModelAdmin):
    list_display = ('posting_number', 'status', 'schema', 'order_number',
                    'needs_attention', 'handled_at', 'updated_at')
    list_filter = ('status', 'schema')
    search_fields = ('posting_number', 'order_number')
    readonly_fields = ('created_at', 'updated_at', 'details', 'duplicates_checked_at')
    actions = ['mark_handled']

    @admin.display(boolean=True, description='Нужен возврат денег')
    def needs_attention(self, obj):
        return obj.needs_attention

    @admin.action(description='Отметить, что деньги возвращены')
    def mark_handled(self, request, queryset):
        updated = queryset.update(handled_at=timezone.now())
        self.message_user(request, f'Отмечено отправлений: {updated}')


@admin.register(OzonReturn)
class OzonReturnAdmin(admin.ModelAdmin):
    list_display = ('return_id', 'posting_number', 'return_type', 'status_name',
                    'needs_attention', 'return_date', 'handled_at')
    list_filter = ('return_type', 'schema', 'status_sys_name')
    search_fields = ('return_id', 'posting_number', 'order_number')
    readonly_fields = ('created_at', 'updated_at', 'details')
    actions = ['mark_handled']

    @admin.display(boolean=True, description='Не разобран')
    def needs_attention(self, obj):
        return obj.needs_attention

    @admin.action(description='Отметить: товар принят, деньги возвращены')
    def mark_handled(self, request, queryset):
        updated = queryset.update(handled_at=timezone.now())
        self.message_user(request, f'Отмечено возвратов: {updated}')
