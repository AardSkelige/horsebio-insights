import uuid

from django.db import models

# Определяем основные группы
GROUP_CHOICES = [
    ('Тара', 'Тара'),
    ('Пробники', 'Пробники'),
    ('Материалы для производства', 'Материалы для производства'),
    ('Товары', 'Товары'),
    ('Этикетки', 'Этикетки')
]


class Counterparty(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование контрагента (покупателя)')
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    is_legacy = models.BooleanField(
        default=False,
        verbose_name='Старый контрагент',
        help_text='Отметьте, если это старая версия существующего контрагента'
    )
    main_counterparty = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='legacy_records',
        verbose_name='Основной контрагент',
        help_text='Укажите основную версию контрагента, если это старая версия'
    )

    @property
    def all_related_ids(self):
        """Получение всех связанных ID контрагентов"""
        if self.is_legacy and self.main_counterparty_id:
            return [self.main_counterparty_id, self.id]
        elif not self.is_legacy:
            legacy_ids = list(self.legacy_records.values_list('id', flat=True))
            return [self.id] + legacy_ids
        return [self.id]

    def __str__(self):
        return f"{self.name}{' (старый)' if self.is_legacy else ''}"

    class Meta:
        db_table = 'parser_counterparty'
        verbose_name = 'Контрагент (покупатель)'
        verbose_name_plural = 'Контрагенты (покупатели)'


class Product(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    uom_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='Единица измерения')
    uom_description = models.CharField(max_length=255, blank=True, null=True, verbose_name='Описание единицы измерения')
    group = models.CharField(max_length=50, choices=GROUP_CHOICES, blank=True, null=True, verbose_name='Группа')
    subgroup = models.CharField(max_length=255, blank=True, null=True, verbose_name='Подгруппа')
    article = models.CharField(max_length=255, blank=True, null=True, verbose_name='Артикул')
    code = models.CharField(max_length=255, blank=True, null=True, verbose_name='Код')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')

    class Meta:
        db_table = 'parser_product'
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['group', 'subgroup', 'name']

        indexes = [
            models.Index(fields=['group']),
            models.Index(fields=['group', 'subgroup']),
        ]

    def __str__(self):
        parts = []
        parts.append(self.name)
        if self.group:
            parts.append(f"({self.group}")
            if self.subgroup:
                parts.append(f" - {self.subgroup})")
            else:
                parts.append(")")
        return " ".join(parts)


class RawMaterial(models.Model):
    name = models.CharField(max_length=255, verbose_name='Наименование')
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    uom_name = models.CharField(max_length=50, blank=True, null=True, verbose_name='Единица измерения')
    uom_description = models.CharField(max_length=255, blank=True, null=True, verbose_name='Описание единицы измерения')
    group = models.CharField(max_length=50, choices=GROUP_CHOICES, blank=True, null=True, verbose_name='Группа')
    article = models.CharField(max_length=255, blank=True, null=True, verbose_name='Артикул')
    code = models.CharField(max_length=255, blank=True, null=True, verbose_name='Код')
    description = models.TextField(blank=True, null=True, verbose_name='Описание')
    lead_time_period_months = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Период расчёта времени доставки (мес)',
        help_text='Если не задано — используется 12 месяцев'
    )

    def __str__(self):
        return f"{self.name} ({self.uom_name})" if self.uom_name else self.name

    def get_group_display(self):
        return dict(GROUP_CHOICES).get(self.group, self.group) if self.group else '-'

    class Meta:
        db_table = 'parser_rawmaterial'
        verbose_name = 'Материал для производства'
        verbose_name_plural = 'Материалы для производства'
        indexes = [
            models.Index(fields=['group']),
        ]


class ProcessingPlan(models.Model):
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    name = models.CharField(max_length=255, verbose_name='Наименование')
    created = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    updated = models.DateTimeField(auto_now=True, verbose_name='Обновлено')
    moysklad_updated = models.DateTimeField(null=True, blank=True, verbose_name='Обновлено в МойСклад')

    def __str__(self):
        return self.name

    class Meta:
        db_table = 'parser_processingplan'
        verbose_name = 'Техкарта'
        verbose_name_plural = 'Техкарты'


class ProcessingPlanMaterial(models.Model):
    processing_plan = models.ForeignKey(ProcessingPlan, on_delete=models.CASCADE, related_name='materials', verbose_name='Техкарта')
    material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, verbose_name='Материал')
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name='Количество')

    class Meta:
        db_table = 'parser_processingplanmaterial'
        unique_together = ('processing_plan', 'material')
        verbose_name = 'Материал техкарты'
        verbose_name_plural = 'Материалы техкарты'

    def __str__(self):
        return f"{self.processing_plan.name} - {self.material.name} ({self.quantity})"


class ProcessingPlanProduct(models.Model):
    processing_plan = models.ForeignKey(ProcessingPlan, on_delete=models.CASCADE, related_name='products', verbose_name='Техкарта')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Продукт')
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name='Количество')

    class Meta:
        db_table = 'parser_processingplanproduct'
        unique_together = ('processing_plan', 'product')
        verbose_name = 'Продукт техкарты'
        verbose_name_plural = 'Продукты техкарты'

    def __str__(self):
        return f"{self.processing_plan.name} - {self.product.name} ({self.quantity})"


class Shipment(models.Model):
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    number = models.CharField(max_length=255, null=True, blank=True, verbose_name='Номер отгрузки')
    date = models.DateTimeField(verbose_name='Дата')
    counterparty = models.ForeignKey(Counterparty, on_delete=models.CASCADE, verbose_name='Контрагент (покупатель)')
    moysklad_updated = models.DateTimeField(null=True, blank=True, verbose_name='Обновлено в МойСклад')

    def __str__(self):
        return f"{self.number or self.external_id} - {self.date}"

    class Meta:
        db_table = 'parser_shipment'
        verbose_name = 'Отгрузка'
        verbose_name_plural = 'Отгрузки'
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['number']),
            models.Index(fields=['date', 'counterparty']),
        ]


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items', verbose_name='Отгрузка')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, verbose_name='Продукт')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Количество')
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Цена')

    @property
    def total_sum(self):
        return float(self.quantity * self.price)

    def debug_info(self):
        return {
            'id': self.id,
            'price': float(self.price),
            'price_type': type(self.price).__name__,
            'quantity': float(self.quantity),
            'total': self.total_sum
        }

    def __str__(self):
        return f"{self.product.name} ({self.quantity})"

    class Meta:
        db_table = 'parser_shipmentitem'
        verbose_name = 'Позиция отгрузки'
        verbose_name_plural = 'Позиции отгрузки'
        indexes = [
            models.Index(fields=['shipment', 'product']),
            models.Index(fields=['product']),
        ]


class RawMaterialUsage(models.Model):
    shipment_item = models.ForeignKey(ShipmentItem, on_delete=models.CASCADE, related_name='raw_material_usages', verbose_name='Позиция отгрузки')
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, verbose_name='Сырьё')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Количество')

    def __str__(self):
        return f"{self.raw_material.name} ({self.quantity})"

    class Meta:
        db_table = 'parser_rawmaterialusage'
        verbose_name = 'Использование материала для производства'
        verbose_name_plural = 'Использование материалов для производства'
        indexes = [
            models.Index(fields=['raw_material', 'shipment_item']),
            models.Index(fields=['shipment_item']),
            models.Index(fields=['raw_material']),
            models.Index(fields=['quantity']),
        ]


class Supply(models.Model):
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    number = models.CharField(max_length=255, null=True, blank=True, verbose_name='Номер')
    date = models.DateTimeField(verbose_name='Дата')
    counterparty = models.ForeignKey(Counterparty, on_delete=models.CASCADE, verbose_name='Поставщик')
    sum = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Сумма')
    moysklad_updated = models.DateTimeField(null=True, blank=True, verbose_name='Обновлено в МойСклад')

    def __str__(self):
        return f"{self.number or self.external_id} от {self.date}"

    class Meta:
        db_table = 'parser_supply'
        verbose_name = 'Приемка'
        verbose_name_plural = 'Приемки'
        ordering = ['-date']


class PurchaseOrder(models.Model):
    external_id = models.CharField(max_length=255, unique=True, verbose_name='Внешний ID')
    number = models.CharField(max_length=255, null=True, blank=True, verbose_name='Номер заказа')
    date = models.DateTimeField(verbose_name='Дата')
    created = models.DateTimeField(verbose_name='Дата создания')
    counterparty = models.ForeignKey(Counterparty, on_delete=models.CASCADE, verbose_name='Поставщик')
    status = models.CharField(max_length=50, blank=True, null=True, verbose_name='Статус')
    sum = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Сумма')
    supplies = models.ManyToManyField(
        Supply,
        related_name='purchase_orders',
        blank=True,
        verbose_name='Связанные приемки'
    )
    moysklad_updated = models.DateTimeField(null=True, blank=True, verbose_name='Обновлено в МойСклад')

    def __str__(self):
        return f"{self.number or self.external_id} от {self.date}"

    @property
    def lead_time(self):
        """Расчет lead time на основе связанных приемок"""
        if self.supplies.exists():
            valid_supply = self.supplies.filter(
                date__gt=self.date
            ).order_by('date').first()

            if valid_supply:
                delta = valid_supply.date - self.date
                return delta.days
        return None

    class Meta:
        db_table = 'parser_purchaseorder'
        verbose_name = 'Заказ поставщику'
        verbose_name_plural = 'Заказы поставщикам'
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['created']),
            models.Index(fields=['status']),
        ]


class PurchaseOrderItem(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заказ поставщику'
    )
    raw_material = models.ForeignKey(
        RawMaterial,
        on_delete=models.CASCADE,
        verbose_name='Материал'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        verbose_name='Количество'
    )
    price = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Цена'
    )
    total = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name='Сумма'
    )
    shipped_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        verbose_name='Принято'
    )
    waiting_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        default=0,
        verbose_name='В ожидании'
    )

    def __str__(self):
        return f"{self.raw_material.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'parser_purchaseorderitem'
        verbose_name = 'Позиция заказа поставщику'
        verbose_name_plural = 'Позиции заказа поставщику'
        indexes = [
            models.Index(fields=['purchase_order', 'raw_material']),
        ]


class SupplyItem(models.Model):
    supply = models.ForeignKey(Supply, on_delete=models.CASCADE, related_name='items', verbose_name='Приемка')
    raw_material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, verbose_name='Материал')
    quantity = models.DecimalField(max_digits=10, decimal_places=3, verbose_name='Количество')
    price = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Цена')
    total = models.DecimalField(max_digits=15, decimal_places=2, verbose_name='Сумма')

    def __str__(self):
        return f"{self.raw_material.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        self.total = self.price * self.quantity
        super().save(*args, **kwargs)

    class Meta:
        db_table = 'parser_supplyitem'
        verbose_name = 'Позиция приемки'
        verbose_name_plural = 'Позиции приемки'


class SyncLock(models.Model):
    """
    Модель для управления блокировками синхронизации.
    Использует SELECT FOR UPDATE для атомарной блокировки.
    """
    LOCK_TYPES = [
        ('moysklad_sync', 'Синхронизация МойСклад'),
    ]

    lock_type = models.CharField(
        max_length=50,
        choices=LOCK_TYPES,
        unique=True,
        verbose_name='Тип блокировки'
    )
    is_locked = models.BooleanField(default=False, verbose_name='Заблокировано')
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='Время блокировки')
    locked_by = models.CharField(max_length=255, null=True, blank=True, verbose_name='Источник блокировки')
    lock_token = models.UUIDField(null=True, blank=True, editable=False, verbose_name='Токен владельца')

    class Meta:
        db_table = 'parser_synclock'
        verbose_name = 'Блокировка синхронизации'
        verbose_name_plural = 'Блокировки синхронизации'

    def __str__(self):
        status = 'заблокирована' if self.is_locked else 'свободна'
        return f"{self.get_lock_type_display()} - {status}"

    @classmethod
    def acquire_lock(cls, lock_type: str, locked_by: str = None, timeout_minutes: int = 60):
        """
        Атомарное получение блокировки с использованием SELECT FOR UPDATE NOWAIT.

        Возвращает уникальный токен владельца или ``None``, если блокировка
        занята. Токен необходимо передавать при продлении и освобождении lock.
        """
        from django.db import transaction
        from django.utils import timezone
        from datetime import timedelta

        try:
            with transaction.atomic():
                lock, created = cls.objects.select_for_update(nowait=True).get_or_create(
                    lock_type=lock_type,
                    defaults={
                        'is_locked': False,
                        'locked_at': None,
                        'locked_by': None
                    }
                )

                if lock.is_locked:
                    lock_age = timezone.now() - lock.locked_at if lock.locked_at else None
                    if lock_age is None or lock_age > timedelta(minutes=timeout_minutes):
                        lock.is_locked = False

                if lock.is_locked:
                    return None

                lock_token = uuid.uuid4()
                lock.is_locked = True
                lock.locked_at = timezone.now()
                lock.locked_by = locked_by
                lock.lock_token = lock_token
                lock.save(update_fields=['is_locked', 'locked_at', 'locked_by', 'lock_token'])

                return str(lock_token)

        except Exception:
            return None

    @classmethod
    def refresh_lock(cls, lock_type: str, lock_token: str) -> bool:
        """Продлевает lease, только если вызывающий процесс всё ещё владелец."""
        from django.utils import timezone

        if not lock_token:
            return False

        try:
            updated = cls.objects.filter(
                lock_type=lock_type,
                is_locked=True,
                lock_token=lock_token,
            ).update(locked_at=timezone.now())
            return updated == 1
        except Exception:
            return False

    @classmethod
    def release_lock(cls, lock_type: str, lock_token: str) -> bool:
        """Освобождает блокировку, только если токен принадлежит владельцу."""
        if not lock_token:
            return False

        updated = cls.objects.filter(
            lock_type=lock_type,
            is_locked=True,
            lock_token=lock_token,
        ).update(
            is_locked=False,
            locked_at=None,
            locked_by=None,
            lock_token=None,
        )
        return updated == 1

    @classmethod
    def is_lock_held(cls, lock_type: str) -> bool:
        """Проверка статуса блокировки (без захвата)."""
        try:
            lock = cls.objects.get(lock_type=lock_type)
            return lock.is_locked
        except cls.DoesNotExist:
            return False
