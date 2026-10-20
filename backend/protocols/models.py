from django.db import models

from core.models import RawMaterial


class ProtocolTemplate(models.Model):
    title = models.CharField(max_length=255, verbose_name='Название')
    file_name = models.CharField(max_length=255, unique=True, verbose_name='Файл')
    content = models.BinaryField(verbose_name='Шаблон Word')
    merge_into = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='merged_from',
        verbose_name='Общий протокол, если в задании несколько таких продуктов',
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        ordering = ['title']
        verbose_name = 'Шаблон протокола'
        verbose_name_plural = 'Шаблоны протоколов'

    def __str__(self):
        return self.title


class TemplateLink(models.Model):
    plan_external_id = models.CharField(max_length=64, unique=True, verbose_name='Техкарта в МойСклад')
    plan_name = models.CharField(max_length=255, verbose_name='Техкарта')
    template = models.ForeignKey(ProtocolTemplate, on_delete=models.CASCADE, related_name='links', verbose_name='Шаблон')

    class Meta:
        verbose_name = 'Шаблон техкарты'
        verbose_name_plural = 'Шаблоны техкарт'

    def __str__(self):
        return f'{self.plan_name} → {self.template.title}'


class TemplateMaterial(models.Model):
    template = models.ForeignKey(ProtocolTemplate, on_delete=models.CASCADE, related_name='materials', verbose_name='Шаблон')
    row_name = models.CharField(max_length=255, verbose_name='Строка в шаблоне')
    material = models.ForeignKey(RawMaterial, on_delete=models.CASCADE, related_name='protocol_rows', verbose_name='Сырьё')

    class Meta:
        unique_together = ('template', 'row_name')
        verbose_name = 'Сырьё строки шаблона'
        verbose_name_plural = 'Сырьё строк шаблонов'


class ManualSeries(models.Model):
    material = models.OneToOneField(RawMaterial, on_delete=models.CASCADE, related_name='manual_series', verbose_name='Сырьё')
    series = models.CharField(max_length=100, blank=True, verbose_name='Серия')
    expiry_date = models.DateField(null=True, blank=True, verbose_name='Годен до')
    manufacturer = models.CharField(max_length=255, blank=True, verbose_name='Производитель')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Серия сырья вне склада'
        verbose_name_plural = 'Серии сырья вне склада'
