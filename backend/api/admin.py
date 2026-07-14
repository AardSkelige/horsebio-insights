from django.contrib import admin

from .models import UserActivityLog


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'created_at', 'ip_address')
    list_filter = ('action', 'created_at')
    search_fields = ('user__username', 'user__email', 'ip_address', 'user_agent')
    readonly_fields = ('user', 'action', 'created_at', 'ip_address', 'user_agent')
