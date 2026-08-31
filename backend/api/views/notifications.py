"""Уведомления: что в разделах требует внимания.

Список считается заново по живым данным при каждом запросе (см.
`api/notifications/core.py`), поэтому эндпоинт только собирает результат
и применяет к нему персональные отметки.

Права проверяются не здесь, а внутри `collect`: раздел, к которому у человека
нет доступа, до него не дойдёт. Сам путь общий — колокольчик есть у всех.
"""

import logging

from rest_framework.decorators import api_view
from rest_framework.response import Response

from api import notifications

logger = logging.getLogger(__name__)


@api_view(["GET"])
def notifications_list(request):
    """Актуальные уведомления пользователя со счётчиками по разделам."""
    refresh = request.GET.get("refresh") == "1"
    return Response(notifications.collect(request.user, refresh=refresh))


@api_view(["POST"])
def notifications_read(request):
    """Отметить уведомления прочитанными или вернуть в непрочитанные.

    Пустой список ключей означает «все». Отметку ставит человек, а не факт
    открытия панели: иначе счётчик гаснет сам собой, и непонятно, почему.
    """
    keys = request.data.get("keys") or []
    read = bool(request.data.get("read", True))
    marked = notifications.mark_read(request.user, keys, read=read)
    # Возвращаем сразу пересчитанный список: интерфейсу не нужен второй запрос,
    # а счётчики не приходится складывать на клиенте по своим правилам
    return Response({"marked": marked, **notifications.collect(request.user)})
