from django.core.management.base import BaseCommand

from protocols.services.legacy_seed import seed


class Command(BaseCommand):
    help = 'Загрузить шаблоны протоколов и связи со старого сайта склада'

    def add_arguments(self, parser):
        parser.add_argument('templates_folder')
        parser.add_argument('db_path')

    def handle(self, *args, templates_folder, db_path, **options):
        result = seed(templates_folder, db_path)
        self.stdout.write(self.style.SUCCESS(
            f"Шаблонов: {result['templates']}, техкарт привязано: {result['linked']}, "
            f"серий вне склада: {result['manual_series']}, строк шаблонов без сырья: {result['unmapped_rows']}"
        ))
        for name in result['unlinked']:
            self.stdout.write(self.style.WARNING(f'Без шаблона: {name}'))
