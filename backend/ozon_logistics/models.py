from django.db import models
from django.utils import timezone


class OzonOAuthToken(models.Model):
    """OAuth-токен частного приложения «OZON Доставка Horse-Bio».

    Запись всегда одна (SINGLETON_PK): у нас один продавец и одно приложение.
    Токен живёт недолго и обновляется по refresh_token, поэтому хранится в БД,
    а не в .env — там лежат только client_id/client_secret.
    """

    SINGLETON_PK = 1

    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    scope = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'OAuth-токен Ozon Доставки'
        verbose_name_plural = 'OAuth-токены Ozon Доставки'

    def __str__(self):
        if self.expires_at:
            return f'Ozon OAuth, истекает {self.expires_at:%Y-%m-%d %H:%M:%S}'
        return 'Ozon OAuth, срок неизвестен'

    def is_expired(self, *, leeway_seconds=60):
        """Истёк ли токен. Запас нужен, чтобы не отправить протухший в полёте."""
        if not self.expires_at:
            return True
        return timezone.now() >= self.expires_at - timezone.timedelta(seconds=leeway_seconds)


class OzonAuthState(models.Model):
    """Одноразовый state для защиты OAuth-редиректа от CSRF.

    Создаётся при старте авторизации, гасится в callback. Пережившие своё
    записи чистит purge_expired() — код авторизации живёт 5 минут, дольше
    держать state незачем.
    """

    LIFETIME = timezone.timedelta(minutes=10)

    state = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'OAuth-state Ozon Доставки'
        verbose_name_plural = 'OAuth-state Ozon Доставки'

    def __str__(self):
        return f'{self.state} ({self.created_at:%Y-%m-%d %H:%M:%S})'

    @classmethod
    def purge_expired(cls):
        cls.objects.filter(created_at__lt=timezone.now() - cls.LIFETIME).delete()


class OzonProduct(models.Model):
    """Сопоставление нашего артикула с идентификаторами товара в Ozon.

    `sku` нужен и для расчёта доставки, и для создания заказа, а получить его
    можно только у Ozon (`/v3/product/list`) — в МойСклад его нет. Дёргать API
    на каждое открытие корзины нельзя, поэтому держим у себя и обновляем
    периодически командой sync_ozon_products.
    """

    offer_id = models.CharField('Артикул (offer_id)', max_length=255, unique=True)
    sku = models.BigIntegerField('SKU в Ozon')
    product_id = models.BigIntegerField('product_id в Ozon', null=True, blank=True)
    name = models.CharField('Название', max_length=500, blank=True)
    has_fbs_stocks = models.BooleanField('Есть остатки FBS', default=False)
    has_fbo_stocks = models.BooleanField('Есть остатки FBO', default=False)
    archived = models.BooleanField('В архиве', default=False)
    synced_at = models.DateTimeField('Обновлено из Ozon', auto_now=True)

    class Meta:
        verbose_name = 'Товар Ozon'
        verbose_name_plural = 'Товары Ozon'
        ordering = ['offer_id']
        indexes = [models.Index(fields=['sku'])]

    def __str__(self):
        return f'{self.offer_id} → sku {self.sku}'

    @property
    def sellable_via_ozon_delivery(self):
        """Годен ли товар для Ozon Доставки.

        Схема MIX: везти могут и с нашего склада (FBS), и со склада Ozon (FBO) —
        достаточно остатка хоть где-то. Без зарегистрированного в Ozon остатка
        заказ создать нельзя вовсе.
        """
        return (self.has_fbs_stocks or self.has_fbo_stocks) and not self.archived


class OzonPickupPoint(models.Model):
    """Пункт выдачи Ozon — локальная копия для карты в корзине.

    Точек около 94 тысяч, и `/v1/delivery/point/list` отдаёт их одним куском без
    пагинации, поэтому дёргать его на каждое открытие корзины нельзя. Держим
    координаты у себя и обновляем раз в сутки.

    Подробности (адрес, часы, рейтинг) живут в отдельном методе, до 100 точек за
    запрос — на весь список это почти тысяча вызовов, поэтому подтягиваем их
    лениво, когда покупатель выбрал конкретный пункт, и сохраняем сюда же.
    """

    map_point_id = models.BigIntegerField('ID точки на карте', primary_key=True)
    latitude = models.FloatField('Широта')
    longitude = models.FloatField('Долгота')

    name = models.CharField('Название', max_length=500, blank=True)
    address = models.CharField('Адрес', max_length=1000, blank=True)
    details = models.JSONField('Подробности из Ozon', null=True, blank=True)
    details_synced_at = models.DateTimeField('Подробности обновлены', null=True, blank=True)

    # Не auto_now: оно не срабатывает в bulk_update, а массовое обновление —
    # основной путь для 94 тысяч точек. Время проставляет сервис.
    synced_at = models.DateTimeField('Координаты обновлены', default=timezone.now)

    class Meta:
        verbose_name = 'Пункт выдачи Ozon'
        verbose_name_plural = 'Пункты выдачи Ozon'
        indexes = [
            # Выборка точек в границах видимой области карты
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return self.address or f'Точка {self.map_point_id}'

    @classmethod
    def in_bounds(cls, *, south, west, north, east, limit=500):
        """Точки внутри прямоугольника карты.

        Лимит нужен, чтобы при сильном отдалении не отдать в браузер десятки
        тысяч меток: столько на карте всё равно не показать.
        """
        return cls.objects.filter(
            latitude__gte=south, latitude__lte=north,
            longitude__gte=west, longitude__lte=east,
        )[:limit]
