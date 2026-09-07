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


class UserHomePreference(models.Model):
    """Персональные настройки главной страницы пользователя."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='home_preference',
    )
    pinned_paths = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user} home preferences'


class UserPageAccess(models.Model):
    """
    Разрешение пользователю на конкретную страницу приложения.
    Наличие строки = доступ есть. Отсутствие = доступа нет («по умолчанию ничего»).
    page_key соответствует реестру api.access.PAGES. Суперпользователь эти строки
    игнорирует — ему доступно всё.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='page_access',
    )
    page_key = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'page_key')
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return f'{self.user} → {self.page_key}'


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

    Заполняется командой run_check после завершения процесса (см. services/script_runner.py),
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


class NotificationState(models.Model):
    """Прочитал ли пользователь уведомление.

    Сами уведомления не хранятся — они каждый раз считаются заново по живым
    данным (см. `api/notifications/core.py`). Здесь только отметка о прочтении.

    Отпечаток (`fingerprint`) описывает суть уведомления. Пока он тот же,
    отметка действует; изменился — уведомление снова непрочитанное. Поэтому
    прочитанное не «прячет» проблему: изменились цифры — оно вернулось.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_states',
    )
    key = models.CharField(max_length=200)
    fingerprint = models.CharField(max_length=100, blank=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'key'], name='uniq_notification_state'),
        ]
        indexes = [models.Index(fields=['user'])]

    def __str__(self):
        return f'{self.user} → {self.key} ({"прочитано" if self.seen_at else "новое"})'


class CdekWaybillState(models.Model):
    """Состояние робота накладных СДЭК: по записи на заказ сайта.

    Раньше лежало в JSON-файле на томе (`.cdek_waybill_state.json`), и держалось
    это на том, что том не забыли смонтировать в docker-compose. Забыли бы —
    робот начал бы с чистого листа и завёл вторую накладную на заказ, который
    уже уехал. Здесь же состояние бэкапится вместе с базой и переживает
    любой деплой.

    Запись хранится целиком в `payload`, а не разложена по колонкам: робот
    дописывает в неё поля по ходу дела (`st.update(fields)`), и жёсткая схема
    молча теряла бы то, чего в ней не предусмотрели.
    """
    order_id = models.CharField(max_length=64, unique=True,
                                verbose_name='Заказ в МойСклад')
    payload = models.JSONField(default=dict, verbose_name='Запись робота')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Накладная СДЭК (состояние робота)'
        verbose_name_plural = 'Накладные СДЭК (состояние робота)'

    def __str__(self):
        name = (self.payload or {}).get('name') or self.order_id
        status = (self.payload or {}).get('status') or 'без статуса'
        return f'Заказ {name} — {status}'


class SiteOrderSnapshot(models.Model):
    """Заказ сайта из выгрузки CommerceML — единственная его копия у нас.

    Сайт отдаёт заказы окном и, получив подтверждение, больше их не отдаёт
    никогда. До 07.09.2026 они лежали в JSON-файле на томе: пропал бы том —
    пропали бы заказы, восстановить их было бы неоткуда. Здесь они бэкапятся
    вместе с базой.

    Запись хранится целиком в `payload` — той же формой, что читает и пишет
    сверка (`SiteOrder.as_dict`). Отдельной колонкой вынесена только дата:
    по ней хранилище чистится от слишком старых.
    """
    order_id = models.CharField(max_length=64, unique=True, verbose_name='Заказ на сайте')
    date = models.CharField(max_length=10, blank=True, db_index=True,
                            verbose_name='Дата заказа')
    payload = models.JSONField(default=dict, verbose_name='Заказ целиком')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Заказ сайта (копия выгрузки)'
        verbose_name_plural = 'Заказы сайта (копия выгрузки)'

    def __str__(self):
        payload = self.payload or {}
        return f"Заказ {payload.get('number') or self.order_id} от {self.date or '—'}"


class SiteOrdersReconcileState(models.Model):
    """Отметки сверки заказов сайта: когда окно последний раз читали и подтверждали.

    Строка одна. Отметки хранятся строками ровно в том виде, в каком их пишет
    сверка: по ним считается, сколько дней сайт молчит, и разбирает их тот же
    код, что и писал.
    """
    last_fetch = models.CharField(max_length=32, blank=True, verbose_name='Последняя выгрузка')
    last_acknowledge = models.CharField(max_length=32, blank=True,
                                        verbose_name='Последнее подтверждение')

    class Meta:
        verbose_name = 'Сверка заказов сайта (отметки)'
        verbose_name_plural = 'Сверка заказов сайта (отметки)'

    def __str__(self):
        return f"выгрузка {self.last_fetch or '—'}, подтверждение {self.last_acknowledge or '—'}"

    @classmethod
    def get(cls):
        """Строка всегда одна и та же.

        Через `first() or create()` два процесса могли завести по строке, и
        отметки второй становились невидимы навсегда: читают всегда первую.
        """
        return cls.objects.get_or_create(pk=1)[0]


class BuyPriceSyncRun(models.Model):
    """Прогон робота закупочных цен: что он сделал и что изменил.

    Раньше все девяносто прогонов лежали одним JSON-файлом на томе
    (`.sync_state.json`), и держалось это на том, что том не забыли
    смонтировать. Пропал бы — робот потерял бы историю изменений цен,
    а восстановить её неоткуда: он показывает, что и когда поменял.

    Строка на прогон. `last_run` и `last_stats`, которые были в файле
    отдельными ключами, — это просто последняя строка, второй копии им незачем.
    """
    # Сколько прогонов храним. Столько же, сколько хранил файл.
    KEEP_RUNS = 90

    date = models.CharField(max_length=32, unique=True, verbose_name='Когда')
    stats = models.JSONField(default=dict, verbose_name='Счётчики')
    changes = models.JSONField(default=list, verbose_name='Что изменилось')
    errors = models.JSONField(default=list, verbose_name='Ошибки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Записан')

    class Meta:
        verbose_name = 'Прогон робота закупочных цен'
        verbose_name_plural = 'Прогоны робота закупочных цен'
        ordering = ['-date']

    def __str__(self):
        stats = self.stats or {}
        return f"{self.date}: обновлено {stats.get('updated', 0)}, ошибок {stats.get('errors', 0)}"
