#!/usr/bin/env python3
"""
Хранилище заказов сайта в базе.

Сайт отдаёт заказы окном и, получив подтверждение, больше их не отдаёт никогда —
эта копия единственная. В файле на томе она держалась на том, что том не забыли
смонтировать; теперь бэкапится вместе с базой.

Форма словаря та же, что была у файла (`orders`, `last_fetch`, `last_acknowledge`),
поэтому сверка о переезде не знает: `reconcile_core` работает с любым хранилищем,
у которого есть load() и save().
"""
from django_env import setup_django


class DbStore:
    """Заказы — по строке на заказ, отметки сверки — одной строкой."""

    def load(self) -> dict:
        setup_django()
        from api.models import SiteOrderSnapshot, SiteOrdersReconcileState

        marks = SiteOrdersReconcileState.get()
        return {
            "orders": {row.order_id: row.payload
                       for row in SiteOrderSnapshot.objects.all()},
            "last_fetch": marks.last_fetch or None,
            "last_acknowledge": marks.last_acknowledge or None,
        }

    def save(self, store: dict) -> None:
        setup_django()
        from django.db import transaction
        from api.models import SiteOrderSnapshot, SiteOrdersReconcileState

        orders = store.get("orders") or {}
        rows = [
            SiteOrderSnapshot(
                order_id=order_id,
                payload=payload,
                # Копия для запросов и админки; в payload дата остаётся как пришла.
                # Обрезаем: в выгрузке она не проверяется ничем, и значение длиннее
                # колонки уронило бы всю запись — каждый раз, пока заказ в окне.
                date=str((payload or {}).get("date") or "")[:10],
            )
            for order_id, payload in orders.items()
        ]

        with transaction.atomic():
            if rows:
                # Один запрос на всё окно вместо пары на каждый заказ: хранилище
                # держит заказы за 400 дней, и построчная запись выливалась бы
                # в тысячи запросов на прогон.
                SiteOrderSnapshot.objects.bulk_create(
                    rows,
                    update_conflicts=True,
                    unique_fields=["order_id"],
                    update_fields=["payload", "date", "updated_at"],
                )

            if orders:
                # Заказов, которых в словаре не осталось, не должно остаться
                # и в базе: сверка чистит слишком старые именно так — выкидывая
                # их из словаря.
                SiteOrderSnapshot.objects.exclude(order_id__in=list(orders)).delete()
            # А вот пустой словарь удалением не считаем. Такую форму отдаёт
            # EMPTY_STORE и чтение отсутствующего файла, и это единственная копия
            # заказов: лучше оставить лишнее, чем стереть всё разом.

            marks = SiteOrdersReconcileState.get()
            marks.last_fetch = store.get("last_fetch") or ""
            marks.last_acknowledge = store.get("last_acknowledge") or ""
            marks.save(update_fields=["last_fetch", "last_acknowledge"])
