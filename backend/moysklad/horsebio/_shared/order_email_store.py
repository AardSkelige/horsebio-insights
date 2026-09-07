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


class StateLockLost(RuntimeError):
    """Замок отпустило переподключение к базе — журнал писать нельзя."""


# Соединение, на котором взят advisory-замок. Он живёт в сессии Postgres,
# а не в приложении: оборвалось соединение — замок снят, и Django об этом
# молчит, он просто подключается заново.
_locked_on = None


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
        global _locked_on
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s)', [LOCK_KEY])
        # Запоминаем само соединение. Внутри замка робот ходит в почту
        # и МойСклад минутами, и за это время соединение может стать негодным
        # (ошибка запроса, перезапуск или таймаут Postgres, CONN_MAX_AGE).
        # Django тогда молча подключится заново — на новом соединении замка
        # уже нет, и второй процесс войдёт в ту же секцию. Ровно так пропал
        # заказ 532598916, только вместо переподключения был файл без flock.
        previous, _locked_on = _locked_on, connection.connection
        try:
            yield
        finally:
            held = connection.connection is _locked_on
            _locked_on = previous
            if held:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK_KEY])
            else:
                # Отпускать нечего: замок ушёл вместе со старым соединением,
                # а pg_advisory_unlock на новом вернул бы false молча.
                print('[order_email_store] ВНИМАНИЕ: соединение с базой '
                      'переоткрылось, замок журнала был потерян')
        return

    from api.models import OrderEmailState

    with transaction.atomic():
        rows = OrderEmailState.objects.filter(pk=1)
        if connection.features.has_select_for_update:
            list(rows.select_for_update())
        yield


def check_lock() -> None:
    """Убедиться, что замок всё ещё наш, — перед тем как писать.

    Read-modify-write под потерянным замком и есть потерянный заказ: пока мы
    ходили в МойСклад, соседний процесс успел записать своё, а мы сохраняем
    поверх прочитанное до него. Лучше упасть: прогон повторится по расписанию,
    а затёртый заказ восстановить неоткуда.
    """
    if _locked_on is None:
        return
    setup_django()
    from django.db import connection

    if connection.vendor == 'postgresql' and connection.connection is not _locked_on:
        raise StateLockLost(
            'Соединение с базой переоткрылось, замок журнала заказов потерян — '
            'запись отменена, чтобы не затереть чужие изменения'
        )


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
    check_lock()
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
    check_lock()
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
