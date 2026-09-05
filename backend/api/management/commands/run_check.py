# api/management/commands/run_check.py
"""
Запуск скрипта проверки по расписанию.

Так его зовёт cron: `docker compose exec -T backend python manage.py run_check
<id>` (обёртка — deploy/cron/horsebio-check.sh). Так же его порождает кнопка
«Запустить» в интерфейсе, только с готовым --run-id. Место запуска одно,
и ночной прогон ничем не отличается от ручного.

Раньше cron ходил сюда через HTTP: `curl` на localhost:8001 с секретом
в crontab открытым текстом. Ради этого приходилось держать открытым порт,
на котором висит админка Django.

Коды выхода: код самого скрипта, 75 — прогон уже идёт (пропуск, не ошибка),
124 — снят по сроку, 3 — не удалось запустить, 2 — нет такого скрипта.
"""
import sys

from django.core.management.base import BaseCommand

from api.services import script_runner
from api.services.scripts_registry import SCRIPTS_CONFIG, SCRIPTS_BY_ID, script_timeout


class Command(BaseCommand):
    help = 'Запустить скрипт проверки и дождаться его завершения'

    def add_arguments(self, parser):
        parser.add_argument(
            'script_id', nargs='?',
            help='Идентификатор из реестра проверок (--list покажет все)',
        )
        parser.add_argument(
            '--run-id',
            help='Готовая метка прогона. Её передаёт интерфейс, чтобы страница '
                 'нашла лог ещё до того, как команда поднимется',
        )
        parser.add_argument(
            '--timeout', type=int,
            help='Предел в секундах вместо взятого из реестра',
        )
        parser.add_argument(
            '--list', action='store_true',
            help='Показать реестр проверок и выйти',
        )

    def handle(self, *args, **options):
        if options['list']:
            self._print_registry()
            return

        script_id = options['script_id']
        if not script_id:
            self.stderr.write('Укажите идентификатор проверки или --list')
            sys.exit(script_runner.EXIT_UNKNOWN)
        if script_id not in SCRIPTS_BY_ID:
            self.stderr.write(f'Неизвестная проверка: {script_id}')
            self.stderr.write('Список: python manage.py run_check --list')
            sys.exit(script_runner.EXIT_UNKNOWN)

        code = script_runner.execute(
            script_id,
            run_id=options['run_id'],
            timeout=options['timeout'],
            log=self.stderr.write,
        )

        # Скрипт, снятый сигналом, отдаёт отрицательный код (-15 для SIGTERM).
        # Наружу такой не выставить, и оболочки давно договорились писать
        # 128 + номер сигнала — cron и обёртка ждут именно этого.
        sys.exit(code if code >= 0 else 128 - code)

    def _print_registry(self):
        for script in SCRIPTS_CONFIG:
            self.stdout.write(
                f'{script["id"]:34} {script["schedule"]:24} '
                f'предел {script_timeout(script["id"])} с   {script["name"]}'
            )
