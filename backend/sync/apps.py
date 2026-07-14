from django.apps import AppConfig
import os
import sys

import logging

logger = logging.getLogger(__name__)


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sync'
    label = 'parser'  # Keep label as 'parser' so migrations continue to work with parser_* tables

    def ready(self):
        """Запускается после инициализации Django"""

        # Избегаем запуска планировщика в миграциях и тестах
        if ("migrate" in sys.argv or
            "collectstatic" in sys.argv or
            "test" in sys.argv or
            "shell" in sys.argv):
            return

        # Защита от двойного запуска в Django автоперезагрузке
        if os.environ.get('RUN_MAIN') != 'true':
            return

        # Импортируем и запускаем планировщик
        try:
            from .scheduler import scheduler
            scheduler.start()
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
