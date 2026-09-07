#!/usr/bin/env python3
"""
Журнал заказов из писем в базе — и замок к нему.

Состояние читают и пишут три процесса: робот чтения почты, робот заведения
заказов и страница «Заказы сайта». Раньше это был один JSON-файл, который
каждый переписывал целиком, — 21.07.2026 так пропал заказ 532598916: один
процесс сохранил свою копию поверх только что записанного другим.

Форма словаря прежняя (`processed_message_ids`, `orders`, `last_checked_date`),
поэтому роботы и страница о переезде почти не знают.
"""
from contextlib import contextmanager

from django_env import setup_django

# Номер замка в Postgres. Число произвольное, но постоянное: по нему процессы
# и находят друг друга.
LOCK_KEY = 8_150_721


@contextmanager
def state_lock():
    """Эксклюзивный замок на цикл «прочитал → поправил → сохранил».

    Раньше это был flock по файлу состояния. Теперь — замок в базе: файла
    больше нет, а процессов осталось четверо (два робота, страница «Заказы
    сайта» и Ozon Доставка), и защищать их надо там же, где лежат данные.

    В Postgres это advisory-замок: он не держит транзакцию открытой, пока
    робот ходит в почту и МойСклад. На других базах (SQLite у разработчика)
    берём строку отметок под транзакцию — слабее, но read-modify-write
    закрывает, а без замка там оставаться нельзя: страница и запущенный
    руками робот — уже два процесса.
    """
    setup_django()
    from django.db import connection, transaction

    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s)', [LOCK_KEY])
            try:
                yield
            finally:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK_KEY])
        return

    from api.models import OrderEmailState

    with transaction.atomic():
        rows = OrderEmailState.objects.filter(pk=1)
        if connection.features.has_select_for_update:
            list(rows.select_for_update())
        yield


def load_state(default: dict = None) -> dict:
    """Прочитать журнал. Вызывать только внутри state_lock()."""
    setup_django()
    from api.models import OrderEmailMessage, OrderEmailOrder, OrderEmailState

    marks = OrderEmailState.get()
    state = dict(default or {})
    state["processed_message_ids"] = list(
        OrderEmailMessage.objects.order_by("id").values_list("message_id", flat=True)
    )
    state["orders"] = {row.order_id: row.payload for row in OrderEmailOrder.objects.all()}
    state["last_checked_date"] = marks.last_checked_date or state.get("last_checked_date")
    return state


def save_state(state: dict) -> None:
    """Сохранить журнал. Вызывать только внутри state_lock().

    Пропавшие записи удаляются: страница «Заказы сайта» убирает заказ из журнала
    именно так — выкидывая его из словаря вместе с отметками его писем. Но пустой
    словарь удалением не считаем: это форма только что заведённого состояния,
    а журнал заказов — единственный.
    """
    setup_django()
    from django.db import transaction
    from api.models import OrderEmailMessage, OrderEmailOrder, OrderEmailState

    orders = state.get("orders") or {}
    message_ids = list(state.get("processed_message_ids") or [])

    with transaction.atomic():
        if orders:
            OrderEmailOrder.objects.bulk_create(
                [OrderEmailOrder(order_id=order_id, payload=payload)
                 for order_id, payload in orders.items()],
                update_conflicts=True,
                unique_fields=["order_id"],
                update_fields=["payload", "updated_at"],
            )
            OrderEmailOrder.objects.exclude(order_id__in=list(orders)).delete()

        if message_ids:
            OrderEmailMessage.objects.bulk_create(
                [OrderEmailMessage(message_id=mid) for mid in message_ids],
                ignore_conflicts=True,
            )
            OrderEmailMessage.objects.exclude(message_id__in=message_ids).delete()

        marks = OrderEmailState.get()
        marks.last_checked_date = str(state.get("last_checked_date") or "")[:32]
        marks.save(update_fields=["last_checked_date", "updated_at"])


def last_checked_at():
    """Когда журнал последний раз менялся. Заменило время изменения файла.

    Строку не заводим: чтение страницы не должно создавать записи, да и время
    «сейчас» у пустого журнала выглядело бы как только что прочитанная почта.
    """
    setup_django()
    from api.models import OrderEmailState

    row = OrderEmailState.objects.filter(pk=1).first()
    return row.updated_at if row else None


def forget_order(order_id: str) -> dict | None:
    """Убрать заказ из журнала вместе с отметками его писем.

    Отдельной операцией, а не «пропал из словаря, сохранили словарь»: сохранение
    пустой журнал удалением не считает (иначе один странный прогон стёр бы всё),
    и удаление единственного заказа так бы просто не сработало.

    Отметки писем отпускаем, чтобы следующая проверка почты разобрала их заново —
    ради этого кнопку «Удалить» и нажимают.
    """
    setup_django()
    from django.db import transaction
    from api.models import OrderEmailMessage, OrderEmailOrder

    with transaction.atomic():
        row = OrderEmailOrder.objects.filter(order_id=order_id).first()
        if row is None:
            return None

        payload = row.payload or {}
        released = [snap.get("message_id")
                    for snap in (payload.get("history") or [])
                    if snap.get("message_id")]
        row.delete()
        if released:
            OrderEmailMessage.objects.filter(message_id__in=released).delete()
        return payload
