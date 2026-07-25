from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'
    label = 'parser'  # Keep label as 'parser' so migrations continue to work with parser_* tables
