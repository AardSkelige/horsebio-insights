from django.contrib import admin

from .models import OzonOAuthToken


@admin.register(OzonOAuthToken)
class OzonOAuthTokenAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'has_refresh_token', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(boolean=True, description='refresh_token')
    def has_refresh_token(self, obj):
        return bool(obj.refresh_token)
