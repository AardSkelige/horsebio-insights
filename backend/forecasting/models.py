# forecasting/models.py
from django.db import models
from core.models import Counterparty

class CounterpartyCategory(models.Model):
    """Категория контрагента по объему продаж"""
    
    CATEGORY_CHOICES = [
        ('large', 'Крупный'),
        ('medium', 'Средний'),
        ('small', 'Мелкий'),
        ('rare_large', 'Редкий крупный'),
    ]

    counterparty = models.OneToOneField(
        Counterparty, 
        on_delete=models.CASCADE,
        related_name='sales_category'
    )
    category = models.CharField(
        max_length=20, 
        choices=CATEGORY_CHOICES
    )
    average_monthly_sales = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text="Среднемесячный объем продаж"
    )
    sales_frequency = models.FloatField(
        help_text="Частота продаж (доля месяцев с продажами)"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Категория контрагента'
        verbose_name_plural = 'Категории контрагентов'