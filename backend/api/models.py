from django.conf import settings
from django.db import models


class UserActivityLog(models.Model):
    ACTION_LOGIN = 'login'
    ACTION_LOGOUT = 'logout'

    ACTION_CHOICES = [
        (ACTION_LOGIN, 'Вход'),
        (ACTION_LOGOUT, 'Выход'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='activity_logs',
    )
    action = models.CharField(max_length=16, choices=ACTION_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user} {self.action} {self.created_at:%Y-%m-%d %H:%M:%S}'


class UserPageEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='page_events',
    )
    page_path = models.CharField(max_length=200)
    page_name = models.CharField(max_length=100)
    duration_seconds = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.user} {self.page_name} {self.duration_seconds}s'


class UserSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_sessions',
    )
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_seen_at']

    def __str__(self):
        return f'{self.user} session {self.session_key[:8]}... @ {self.ip_address}'


class HealthCheckException(models.Model):
    """Исключение (подтверждённая ложная тревога) проверки здоровья себестоимости.

    Источник истины — БД. Перед каждым запуском health_check бэкенд экспортирует
    эти записи в data/*.json в формате, который читает скрипт (см. services/health_checks.py).
    """
    KIND_ENTERS        = 'enters'
    KIND_LOSSES        = 'losses'
    KIND_INVENTORIES   = 'inventories'
    KIND_MOVES         = 'moves'
    KIND_SUPPLIES      = 'supplies'
    KIND_SALESRETURNS  = 'salesreturns'
    KIND_ENTER_ZERO    = 'enter_zero'
    KIND_DEVIATIONS    = 'deviations'
    KIND_SUPPLY_JUMPS  = 'supply_jumps'

    KIND_CHOICES = [
        (KIND_ENTERS,       'Оприходования на внутренних складах'),
        (KIND_LOSSES,       'Списания'),
        (KIND_INVENTORIES,  'Инвентаризации'),
        (KIND_MOVES,        'Перемещения'),
        (KIND_SUPPLIES,     'Приёмки'),
        (KIND_SALESRETURNS, 'Возвраты от покупателей'),
        (KIND_ENTER_ZERO,   'Оприходования с нулевой ценой'),
        (KIND_DEVIATIONS,   'Отклонения FIFO vs приёмка'),
        (KIND_SUPPLY_JUMPS, 'Скачки цен в приёмках'),
    ]

    # Типы, чьи исключения хранятся как список {doc_id, ...} (acknowledged)
    ACK_KINDS = {
        KIND_ENTERS, KIND_LOSSES, KIND_INVENTORIES, KIND_MOVES,
        KIND_SUPPLIES, KIND_SALESRETURNS, KIND_ENTER_ZERO,
    }

    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    # Идентичность находки: doc_id (UUID документа) / product_code / name товара
    key = models.CharField(max_length=120)
    label = models.CharField(max_length=255, blank=True)
    reason = models.TextField(blank=True)
    # Доп. поля по типу: store, date, doc_date, status, checked
    extra = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='health_check_exceptions',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['kind', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['kind', 'key'], name='uniq_healthcheck_exception'),
        ]
        indexes = [
            models.Index(fields=['kind']),
        ]

    def __str__(self):
        return f'{self.kind}:{self.key} {self.label}'.strip()


class CheckRunResult(models.Model):
    """Снимок структурированного результата одного запуска health_check.

    Заполняется watcher-потоком после завершения процесса (см. scripts_monitor._run_script_async),
    парсингом <run>.results.json. Используется для истории, дельт и просмотра прошлых запусков
    независимо от очистки лог-файлов.
    """
    script_id = models.CharField(max_length=80, db_index=True)
    run_id = models.CharField(max_length=40)
    finished_at = models.DateTimeField(null=True, blank=True)
    exit_code = models.IntegerField(null=True, blank=True)
    duration_sec = models.FloatField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)   # счётчики severity и по категориям
    findings = models.JSONField(default=list, blank=True)  # стандартизированные категории находок
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-finished_at', '-created_at']
        constraints = [
            models.UniqueConstraint(fields=['script_id', 'run_id'], name='uniq_checkrun_result'),
        ]
        indexes = [
            models.Index(fields=['script_id', '-finished_at']),
        ]

    def __str__(self):
        return f'{self.script_id} {self.run_id} (exit={self.exit_code})'
