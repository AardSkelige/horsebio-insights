#!/usr/bin/env python3
"""
История прогонов робота закупочных цен в базе.

Раньше девяносто прогонов лежали одним JSON-файлом на томе. Форма словаря
осталась прежней (`last_run`, `last_stats`, `history`), поэтому сам робот
о переезде не знает — поменялись только чтение и запись.
"""
from django_env import setup_django


class DbStore:
    """Строка на прогон. `last_run` и `last_stats` — последняя из них."""

    def _as_dict(self, row) -> dict:
        return {"date": row.date, "stats": row.stats,
                "changes": row.changes, "errors": row.errors}

    def load(self) -> dict:
        """Прогоны по возрастанию даты.

        Дату пишет сам робот, всегда в виде `%Y-%m-%d %H:%M` — такие строки
        сортируются как даты. Поменять формат, не поменяв здесь сортировку,
        нельзя: последний прогон окажется не последним, и робот покажет
        в отчёте чужие числа.
        """
        setup_django()
        from api.models import BuyPriceSyncRun

        history = [self._as_dict(row)
                   for row in BuyPriceSyncRun.objects.order_by("date")]
        return {
            "last_run": history[-1]["date"] if history else None,
            "last_stats": history[-1]["stats"] if history else {},
            "history": history,
        }

    def save(self, state: dict) -> None:
        setup_django()
        from django.db import transaction
        from api.models import BuyPriceSyncRun

        history = state.get("history") or []
        rows = [
            BuyPriceSyncRun(
                date=str(run.get("date") or "")[:32],
                stats=run.get("stats") or {},
                changes=run.get("changes") or [],
                errors=run.get("errors") or [],
            )
            for run in history if run.get("date")
        ]
        if not rows:
            # Пустая история — это форма только что заведённого состояния,
            # а не команда «сотри всё». Историю изменений цен восстановить
            # неоткуда, поэтому такую запись просто пропускаем.
            return

        with transaction.atomic():
            BuyPriceSyncRun.objects.bulk_create(
                rows,
                update_conflicts=True,
                unique_fields=["date"],
                update_fields=["stats", "changes", "errors"],
            )
            # Робот сам подрезает историю до HISTORY_KEEP, выкидывая старые
            # прогоны из списка: в базе они тоже не должны оставаться, иначе
            # следующая загрузка их воскресит.
            BuyPriceSyncRun.objects.exclude(
                date__in=[row.date for row in rows]
            ).delete()
