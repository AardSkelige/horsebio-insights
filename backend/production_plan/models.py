from django.db import models


class OzonMonthSales(models.Model):
    month = models.DateField(verbose_name='Месяц')
    article = models.CharField(max_length=64, verbose_name='Артикул')
    quantity = models.PositiveIntegerField(verbose_name='Заказано без отмен, шт')
    synced_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        unique_together = ('month', 'article')
        verbose_name = 'Продажи Ozon за месяц'
        verbose_name_plural = 'Продажи Ozon по месяцам'


class Exclusion(models.Model):
    text = models.CharField(max_length=255, unique=True, verbose_name='Артикул или слово в названии')
    note = models.CharField(max_length=255, blank=True, verbose_name='Товар')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Добавлено')

    class Meta:
        ordering = ['text']
        verbose_name = 'Исключение из плана'
        verbose_name_plural = 'Исключения из плана'

    def __str__(self):
        return self.text


class GreenItem(models.Model):
    article = models.CharField(max_length=64, unique=True, verbose_name='Артикул')
    name = models.CharField(max_length=255, blank=True, verbose_name='Товар')

    class Meta:
        ordering = ['article']
        verbose_name = 'Товар зелёного списка'
        verbose_name_plural = 'Зелёный список'

    def __str__(self):
        return self.article


class WbOrder(models.Model):
    srid = models.CharField(max_length=128, unique=True, verbose_name='Заказ в WB')
    date = models.DateTimeField(verbose_name='Оформлен')
    article = models.CharField(max_length=64, verbose_name='Артикул')
    is_cancel = models.BooleanField(default=False, verbose_name='Отменён')

    class Meta:
        indexes = [models.Index(fields=['date'])]
        verbose_name = 'Заказ WB'
        verbose_name_plural = 'Заказы WB'


class WbSync(models.Model):
    covered_from = models.DateField(verbose_name='Заказы есть начиная с')
    synced_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Загрузка заказов WB'
        verbose_name_plural = 'Загрузка заказов WB'
