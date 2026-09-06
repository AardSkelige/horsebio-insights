# sync/management/commands/sync_data.py
"""
Синхронизация данных МойСклад отдельным процессом.

Так её запускает кнопка «Обновить» (порождает эту команду и забывает про неё)
и так же — расписание. Внутри веб-процесса синхронизация больше не идёт:
gunicorn перезапускает воркер по счётчику запросов и оборвал бы её на середине.

Коды выхода: 0 — готово, 1 — ошибка, 75 — уже идёт (пропуск, не ошибка).
"""
import sys
from datetime import datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sync import runner


class Command(BaseCommand):
    help = 'Синхронизировать данные МойСклад за период'

    def add_arguments(self, parser):
        parser.add_argument('--run-id', type=int,
                            help='Номер уже заведённого прогона (его передаёт кнопка)')
        parser.add_argument('--months', type=int,
                            help='За сколько месяцев назад синхронизировать')
        parser.add_argument('--days', type=int,
                            help='За сколько дней назад синхронизировать')
        parser.add_argument('--start-date', help='Начало периода, ГГГГ-ММ-ДД')
        parser.add_argument('--end-date', help='Конец периода, ГГГГ-ММ-ДД')
        parser.add_argument('--triggered-by', default='кнопка',
                            help='Кто запустил — для журнала прогонов')

    def handle(self, *args, **options):
        code = runner.execute(
            triggered_by=options['triggered_by'],
            run_id=options['run_id'],
            auto_sync=options['triggered_by'] != 'кнопка',
            log=self.stderr.write,
            **self._period(options),
        )
        sys.exit(code)

    def _period(self, options):
        """Либо пара дат, либо число месяцев назад — обходы разные."""
        if bool(options['start_date']) != bool(options['end_date']):
            # Иначе команда молча синхронизировала бы неделю вместо запрошенного.
            raise CommandError('Нужны обе даты: --start-date и --end-date')

        if options['start_date'] and options['end_date']:
            start = datetime.strptime(options['start_date'], '%Y-%m-%d')
            end = datetime.strptime(options['end_date'], '%Y-%m-%d').replace(
                hour=23, minute=59, second=59
            )
            return {'start_date': timezone.make_aware(start),
                    'end_date': timezone.make_aware(end)}

        if options['months']:
            return {'months_back': options['months']}

        end_date = timezone.now()
        return {'start_date': end_date - timedelta(days=options['days'] or 7),
                'end_date': end_date}
