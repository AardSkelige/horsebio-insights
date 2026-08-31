from django.contrib import admin

from .models import OzonOAuthToken, OzonProduct


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
