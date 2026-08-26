"""Ретеншен журнала запусков проверок.

Три робота ходят по расписанию каждые 5 минут и при каждом запуске пишут
в `api_checkrunresult` полный снимок находок — не изменения, а состояние
целиком. К 26 августа 2026 таблица весила 132 МБ при 280 МБ всей базы,
и 97% её строк не читал никто.

Глубже 60 записей на скрипт интерфейс не показывает никогда:
  latest  — 1 запись   (views/checks.py, список карточек)
  history — 30 последних
  recent_changes — 60 последних за 14 дней

Поэтому по умолчанию оставляем 100 — запас в полтора раза от читаемого.

Настоящее лечение — не писать 6 КБ снимка на каждый холостой прогон,
но пока роботы пишут, кто-то должен подметать.
"""
from django.core.management.base import BaseCommand
from django.db import connection

KEEP_DEFAULT = 100


class Command(BaseCommand):
    help = 'Удалить старые записи журнала проверок, оставив N последних на скрипт'

    def add_arguments(self, parser):
        parser.add_argument(
            '--keep', type=int, default=KEEP_DEFAULT,
            help=f'Сколько последних прогонов оставить на скрипт (по умолчанию {KEEP_DEFAULT})',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Показать, что было бы удалено, ничего не трогая',
        )
        parser.add_argument(
            '--vacuum', action='store_true',
            help='После удаления вернуть место операционной системе (VACUUM FULL, '
                 'берёт исключительную блокировку таблицы на время работы)',
        )

    def handle(self, *args, **options):
        from api.models import CheckRunResult

        keep = options['keep']
        dry_run = options['dry_run']

        if keep < 60:
            # Ниже 60 интерфейс начнёт терять данные на экране «недавние изменения»
            self.stderr.write(self.style.ERROR(
                f'--keep={keep}: меньше 60 нельзя, столько читает страница проверок'))
            return

        total_before = CheckRunResult.objects.count()

        with connection.cursor() as cur:
            cur.execute("""
                SELECT script_id, count(*)
                FROM (
                    SELECT script_id,
                           row_number() OVER (PARTITION BY script_id
                                              ORDER BY finished_at DESC) AS rn
                    FROM api_checkrunresult
                ) r
                WHERE rn > %s
                GROUP BY script_id
                ORDER BY 2 DESC
            """, [keep])
            doomed = cur.fetchall()

        if not doomed:
            self.stdout.write(f'Чистить нечего: {total_before} записей, '
                              f'ни у одного скрипта не больше {keep}')
            return

        for script_id, n in doomed:
            self.stdout.write(f'  {script_id:<34} лишних: {n}')
        total_doomed = sum(n for _, n in doomed)

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'\n[dry-run] удалилось бы {total_doomed} из {total_before}, '
                f'осталось бы {total_before - total_doomed}'))
            return

        with connection.cursor() as cur:
            cur.execute("""
                DELETE FROM api_checkrunresult
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id, row_number() OVER (PARTITION BY script_id
                                                      ORDER BY finished_at DESC) AS rn
                        FROM api_checkrunresult
                    ) r WHERE rn > %s
                )
            """, [keep])
            deleted = cur.rowcount

        total_after = CheckRunResult.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'\nУдалено {deleted}, осталось {total_after} (было {total_before})'))

        if options['vacuum']:
            # autovacuum пометит место свободным для переиспользования, но файл
            # на диске не уменьшит. VACUUM FULL уменьшит — ценой блокировки.
            self.stdout.write('VACUUM FULL...')
            with connection.cursor() as cur:
                cur.execute('VACUUM (FULL, ANALYZE) api_checkrunresult')
            self.stdout.write(self.style.SUCCESS('место возвращено системе'))
