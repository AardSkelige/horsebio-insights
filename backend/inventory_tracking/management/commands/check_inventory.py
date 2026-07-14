from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Запустить проверку инвентаризации вручную'

    def add_arguments(self, parser):
        parser.add_argument(
            '--triggered-by',
            default='manual',
            help='Источник запуска (manual|scheduler)',
        )

    def handle(self, *args, **options):
        from inventory_tracking.services.inventory_checker import InventoryChecker

        triggered_by = options['triggered_by']
        self.stdout.write(f'Запуск проверки инвентаризации (triggered_by={triggered_by})...')

        try:
            checker = InventoryChecker()
            run = checker.run(triggered_by=triggered_by)
            self.stdout.write(self.style.SUCCESS(
                f'Готово. Run #{run.id}: '
                f'всего={run.total_products}, '
                f'были={run.inventoried_count}, '
                f'не были={run.not_inventoried_count}'
            ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Ошибка: {e}'))
            raise
