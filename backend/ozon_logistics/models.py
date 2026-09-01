import uuid

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


class OzonDeliveryQuote(models.Model):
    """Рассчитанный вариант доставки, выбранный покупателем в корзине.

    Ozon разрешает создавать заказ только после оплаты, а оплата у нас
    подтверждается письмом через несколько минут. К этому моменту исходный
    расчёт нужно откуда-то взять — здесь он и лежит: `checkout_response`
    хранится целиком, из него собирается запрос на создание заказа.
    """

    STATUS_NEW = 'new'
    STATUS_ORDERED = 'ordered'
    STATUS_FAILED = 'failed'
    # Ozon не ответил вовремя: заказ мог создаться, а мог и нет. Повторять
    # вслепую нельзя — покупатель получит две посылки, поэтому нужен человек.
    STATUS_UNKNOWN = 'unknown'
    STATUS_CHOICES = [
        (STATUS_NEW, 'Рассчитан'),
        (STATUS_ORDERED, 'Заказ создан в Ozon'),
        (STATUS_FAILED, 'Ошибка создания'),
        (STATUS_UNKNOWN, 'Исход неизвестен — проверьте в Ozon'),
    ]

    # Сколько раз пробуем создать заказ, прежде чем перестать долбить Ozon
    MAX_ATTEMPTS = 5

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField('Телефон покупателя', max_length=20)
    items = models.JSONField('Состав: sku и количество')

    map_point_id = models.BigIntegerField('Пункт выдачи', null=True, blank=True)
    courier_address = models.JSONField('Адрес курьерской доставки', null=True, blank=True)

    checkout_response = models.JSONField('Ответ Ozon на расчёт')
    delivery_cost = models.DecimalField(
        'Стоимость логистики, ₽', max_digits=10, decimal_places=2, null=True, blank=True
    )

    status = models.CharField('Статус', max_length=16, choices=STATUS_CHOICES, default=STATUS_NEW)
    site_order_id = models.CharField('Заказ сайта', max_length=64, blank=True, db_index=True)
    order_number = models.CharField('Номер заказа в Ozon', max_length=64, blank=True)
    postings = models.JSONField('Номера отправлений', null=True, blank=True)
    error = models.TextField('Ошибка создания', blank=True)
    attempts = models.PositiveSmallIntegerField('Попыток создания', default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    ordered_at = models.DateTimeField('Заказ создан', null=True, blank=True)

    class Meta:
        verbose_name = 'Расчёт доставки Ozon'
        verbose_name_plural = 'Расчёты доставки Ozon'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.id} · {self.get_status_display()}'

    @property
    def age(self):
        return timezone.now() - self.created_at

    @property
    def needs_order(self):
        """Стоит ли ещё пытаться создать заказ по этому расчёту."""
        if self.status in (self.STATUS_ORDERED, self.STATUS_UNKNOWN):
            return False
        return self.attempts < self.MAX_ATTEMPTS

    @property
    def splits(self):
        return self.checkout_response.get('splits') or []

    @property
    def is_deliverable(self):
        """Есть ли хоть один доступный вариант доставки.

        Ozon помечает недоступный вариант через commissions = null и
        объясняет причину в unavailable_reason.
        """
        return any(split.get('commissions') for split in self.splits)

    def unavailable_reasons(self):
        """Причины, по которым доставка невозможна — для показа покупателю."""
        reasons = []
        for split in self.splits:
            for reason in (split.get('unavailable_reason'),
                           (split.get('delivery_method') or {}).get('unavailable_reason')):
                if reason and reason != 'UNSPECIFIED':
                    reasons.append(reason)
        return sorted(set(reasons))


class OzonPosting(models.Model):
    """Отправление заказа Ozon — то, что реально едет покупателю.

    Заказ дробится на отправления по складам, и статус живёт именно у них.
    Отслеживаем, чтобы вовремя увидеть отмену или невыкуп: деньги у нас, а
    покупатель остался без товара — вернуть их должен человек.
    """

    SCHEMA_FBS = 'fbs'
    SCHEMA_FBO = 'fbo'
    SCHEMA_CHOICES = [(SCHEMA_FBS, 'FBS — наш склад'), (SCHEMA_FBO, 'FBO — склад Ozon')]

    # Статусы, после которых отправление больше не изменится
    FINAL_STATUSES = {'delivered', 'cancelled', 'not_accepted'}
    # Требуют вмешательства: товар не уехал или вернулся, а деньги у нас
    ALARMING_STATUSES = {'cancelled', 'not_accepted'}

    posting_number = models.CharField('Номер отправления', max_length=64, primary_key=True)
    order_number = models.CharField('Номер заказа Ozon', max_length=64, db_index=True)
    quote = models.ForeignKey(
        OzonDeliveryQuote, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='postings_tracked', verbose_name='Расчёт',
    )
    schema = models.CharField('Схема', max_length=8, choices=SCHEMA_CHOICES)
    status = models.CharField('Статус', max_length=64, blank=True)
    cancel_reason = models.CharField('Причина отмены', max_length=500, blank=True)
    details = models.JSONField('Ответ Ozon', null=True, blank=True)

    handled_at = models.DateTimeField('Отработано человеком', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Отправление Ozon'
        verbose_name_plural = 'Отправления Ozon'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.posting_number} · {self.status or "без статуса"}'

    @property
    def is_final(self):
        return self.status in self.FINAL_STATUSES

    @property
    def needs_attention(self):
        """Отправление не доехало, а деньги покупателя у нас — нужен возврат."""
        return self.status in self.ALARMING_STATUSES and self.handled_at is None


class OzonReturn(models.Model):
    """Возврат по нашему отправлению: товар физически едет обратно.

    Это не то же самое, что отменённое отправление: отмена — статус доставки, а
    возврат — конкретная посылка, которую надо принять на складе. Полный возврат
    означает, что покупателю причитается вся сумма, частичный — только за
    отказанные позиции.
    """

    TYPE_FULL = 'FullReturn'
    TYPE_PARTIAL = 'PartialReturn'

    return_id = models.CharField('ID возврата в Ozon', max_length=64, primary_key=True)
    posting_number = models.CharField('Отправление', max_length=64, db_index=True)
    order_number = models.CharField('Заказ Ozon', max_length=64, blank=True)
    quote = models.ForeignKey(
        OzonDeliveryQuote, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='returns', verbose_name='Расчёт',
    )

    return_type = models.CharField('Тип возврата', max_length=32, blank=True)
    schema = models.CharField('Схема', max_length=16, blank=True)
    reason = models.CharField('Причина', max_length=500, blank=True)
    status_name = models.CharField('Статус', max_length=200, blank=True)
    status_sys_name = models.CharField('Системный статус', max_length=100, blank=True)
    return_date = models.DateTimeField('Дата возврата', null=True, blank=True)
    details = models.JSONField('Ответ Ozon', null=True, blank=True)

    handled_at = models.DateTimeField('Отработано человеком', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Возврат Ozon'
        verbose_name_plural = 'Возвраты Ozon'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.return_id} · {self.posting_number}'

    @property
    def is_full(self):
        return self.return_type == self.TYPE_FULL

    @property
    def needs_attention(self):
        """Возврат ещё не разобран: товар принять, деньги вернуть."""
        return self.handled_at is None
