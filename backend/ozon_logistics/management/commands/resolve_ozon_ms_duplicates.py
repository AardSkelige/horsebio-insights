"""Переносит сведения об отправлении в заказ сайта и удаляет дубль от синхронизации."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.ms_duplicates import (
    MoyskladError, find_duplicates, resolve_duplicate,
)


class Command(BaseCommand):
    help = ('Убирает дубли заказов в МойСклад по отправлениям Ozon. '
            'Без --apply только показывает, что будет сделано')

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20,
                            help='Сколько последних отправлений проверить')
        parser.add_argument('--apply', action='store_true',
                            help='Действительно перенести данные и удалить дубли')

    def handle(self, *args, **options):
        apply = options['apply']
        try:
            pairs = find_duplicates(limit=options['limit'])
        except MoyskladError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        transferred = deleted = 0
        for pair in pairs:
            try:
                result = resolve_duplicate(pair, apply=apply)
            except MoyskladError as exc:
                self.stderr.write(self.style.ERROR(f"{pair['posting_number']}: {exc}"))
                continue

            if not result['deleted'] and not result['skipped']:
                continue

            self.stdout.write('')
            self.stdout.write(f"Отправление {result['posting_number']}")

            if result['transferred']:
                transferred += 1
                self.stdout.write('  сведения перенесены в заказ сайта')
            for name in result['deleted']:
                deleted += 1
                self.stdout.write(self.style.WARNING(f'  дубль №{name} удалён'))
            for name, reason in result['skipped']:
                self.stdout.write(f"  пропущен {name or 'документ'}: {reason}")

        self.stdout.write('')
        self.stdout.write(f'Перенесено сведений: {transferred}, удалено дублей: {deleted}')
        if not apply:
            self.stdout.write(self.style.WARNING(
                'Это пробный прогон — ничего не изменено. Повторите с --apply'
            ))
