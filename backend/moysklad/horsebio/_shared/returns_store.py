#!/usr/bin/env python3
"""
Состояние монитора возвратов в базе.

Отметки «этот заказ уже разобран» — единственное, что не даёт роботу завести
документ возврата дважды: у ВБ и Озона один и тот же возврат приходит несколько
раз. В файле на томе они держались на том, что том не забыли смонтировать.

Форма словаря прежняя (`last_run`, `processed_orders`), сам монитор о переезде
не знает.
"""
from django_env import setup_django

START_DATE_FALLBACK = ""


class DbStore:
    """Отметки — по строке на заказ, «докуда дошли» — одной строкой."""

    def load(self, default_last_run: str = "") -> dict:
        setup_django()
        from api.models import ReturnProcessedOrder, ReturnsMonitorState

        marks = ReturnsMonitorState.get()
        return {
            "last_run": marks.last_run or default_last_run,
            "processed_orders": {row.order_id: row.payload
                                 for row in ReturnProcessedOrder.objects.all()},
        }

    def save(self, state: dict, replace: bool = False) -> None:
        """Записать состояние. `replace` — прогон с `--force`: разбор начат
        заново, и прежние отметки уходят вместе с записью новых.

        Почему замена здесь, а не отдельным сбросом до прогона: `--force`
        ходит в МойСклад и к маркетплейсам минутами и может оборваться
        (5xx, лимит запросов, убитый контейнер). Сброс заранее в этом случае
        стирал бы полторы тысячи отметок насовсем, не записав ничего взамен, —
        и следующий обычный прогон завёл бы документы возврата повторно.
        """
        setup_django()
        from django.db import transaction
        from api.models import ReturnProcessedOrder, ReturnsMonitorState

        processed = state.get("processed_orders") or {}
        rows = [ReturnProcessedOrder(order_id=order_id, payload=payload)
                for order_id, payload in processed.items()]

        with transaction.atomic():
            if rows:
                ReturnProcessedOrder.objects.bulk_create(
                    rows,
                    update_conflicts=True,
                    unique_fields=["order_id"],
                    update_fields=["payload", "updated_at"],
                )
                if replace:
                    ReturnProcessedOrder.objects.exclude(
                        order_id__in=list(processed)
                    ).delete()
            # При обычной записи не удаляем ничего: робот отметки не чистит,
            # они только копятся. И пустой словарь удалением не считаем даже
            # при `replace` — прогон, не нашедший ни одного заказа, чаще
            # означает сбой опроса, чем «забудь всё». Стереть отметки, ничего
            # не разобрав, — отдельное осознанное действие, см. reset().
            marks = ReturnsMonitorState.get()
            marks.last_run = str(state.get("last_run") or "")[:32]
            marks.save(update_fields=["last_run"])

    def reset(self) -> int:
        """Забыть все отметки — прогон с `--force` проверяет всё заново.

        Отдельным действием, а не «сохранением пустого словаря»: удаление
        полутора тысяч отметок должно быть видно в коде, а не случаться
        побочным эффектом обычной записи.
        """
        setup_django()
        from api.models import ReturnProcessedOrder

        removed, _ = ReturnProcessedOrder.objects.all().delete()
        return removed
