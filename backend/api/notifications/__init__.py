"""Уведомления Insights.

Механизм общий для всех разделов: ядро в `core`, поводы — в модулях-провайдерах
рядом. Чтобы подключить новый раздел, достаточно написать функцию с декоратором
`@provider('<ключ страницы>')` и импортировать её модуль здесь.

    from .core import Notification, WARNING, provider

    @provider('deadlines')
    def overdue_invoices():
        yield Notification(key='deadlines:overdue:42', level=WARNING, ...)

Импорты провайдеров ниже — единственное место, где они регистрируются, поэтому
без строчки здесь раздел молчит.
"""

from .core import (  # noqa: F401
    CRITICAL, INFO, LEVELS, WARNING, Notification, active, collect, invalidate,
    mark_read, provider,
)

from . import discounted  # noqa: F401,E402  — регистрирует провайдер раздела
