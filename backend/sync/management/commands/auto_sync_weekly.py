# sync/management/commands/auto_sync_weekly.py
"""
Ночная синхронизация за последнюю неделю.

Тонкая обёртка над `sync_data`: сама синхронизация — в `sync/runner.py`,
одна на все способы запуска. Команда осталась отдельной, потому что на неё
ссылается реестр проверок (`horsebio_data_sync`) и строка в crontab,
а ещё она ставит отметку о времени последнего автопрогона.
"""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache
from django.utils import timezone

from sync import runner

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Автоматическая синхронизация данных за последнюю неделю'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Показать что будет синхронизировано без фактического выполнения'
        )

    def handle(self, *args, **options):
        end_date = timezone.now()
        start_date = end_date - timedelta(days=7)
        period = f'{start_date.strftime("%d.%m.%Y")} - {end_date.strftime("%d.%m.%Y")}'

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'DRY RUN: Будет синхронизирован период {period}'))
            return

        self.stdout.write(self.style.SUCCESS(f'Начало автоматической синхронизации: {period}'))

        code = runner.execute(
            start_date=start_date,
            end_date=end_date,
            triggered_by='расписание',
            auto_sync=True,
            log=lambda message: self.stdout.write(self.style.ERROR(message)),
        )

        if code == runner.EXIT_BUSY:
            # Не ошибка: очередь синхронизаций хуже пропущенного запуска.
            self.stdout.write(self.style.WARNING('Синхронизация уже выполняется. Пропускаем.'))
            return

        if code != runner.EXIT_OK:
            raise CommandError('Синхронизация не была завершена')

        # Отметка о свежести данных: по ней страница показывает предупреждение,
        # если автосинхронизация давно не проходила.
        cache.set('last_auto_sync_started', timezone.now(), timeout=None)

        self.stdout.write(self.style.SUCCESS('Автоматическая синхронизация завершена'))
        logger.info('Auto sync completed, period: %s', period)
