from django.db import models

from core.models import RawMaterial

QUANTITY = {'max_digits': 14, 'decimal_places': 3}


class Slot(models.Model):
    external_id = models.CharField(max_length=64, unique=True, verbose_name='ID в МойСклад')
    name = models.CharField(max_length=64, verbose_name='Ячейка')

    class Meta:
        ordering = ['name']
        verbose_name = 'Ячейка'
        verbose_name_plural = 'Ячейки'

    def __str__(self):
        return self.name


class MaterialStock(models.Model):
    material = models.OneToOneField(RawMaterial, on_delete=models.CASCADE, related_name='stock', verbose_name='Сырьё')
    slot = models.ForeignKey(Slot, null=True, blank=True, on_delete=models.SET_NULL, related_name='stocks', verbose_name='Ячейка')
    quantity = models.DecimalField(default=0, verbose_name='Остаток в МойСклад', **QUANTITY)
    synced_at = models.DateTimeField(null=True, blank=True, verbose_name='Сверено с МойСклад')

    class Meta:
        verbose_name = 'Остаток сырья'
        verbose_name_plural = 'Остатки сырья'

    def __str__(self):
        return f'{self.material.name}: {self.quantity}'


class Batch(models.Model):
    material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, related_name='batches', verbose_name='Сырьё')
    series = models.CharField(max_length=100, blank=True, verbose_name='Серия')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Годен до')
    manufacturer = models.CharField(max_length=255, blank=True, verbose_name='Производитель')
    quantity = models.DecimalField(default=0, verbose_name='Остаток', **QUANTITY)
    received_at = models.DateTimeField(verbose_name='Принята')

    class Meta:
        ordering = [models.F('expiry_date').asc(nulls_last=True), 'received_at']
        verbose_name = 'Серия'
        verbose_name_plural = 'Серии'

    def __str__(self):
        return f'{self.material.name}: {self.series or "без серии"}'


class BatchMovement(models.Model):
    IMPORT = 'import'
    RECONCILE = 'reconcile'
    KINDS = [(IMPORT, 'Перенос с сайта склада'), (RECONCILE, 'Сверка с МойСклад')]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='movements', verbose_name='Серия')
    kind = models.CharField(max_length=20, choices=KINDS, verbose_name='Что произошло')
    quantity = models.DecimalField(verbose_name='Изменение', **QUANTITY)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда')

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Движение серии'
        verbose_name_plural = 'Движения серий'
