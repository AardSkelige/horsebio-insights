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
