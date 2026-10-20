from django.core.management.base import BaseCommand, CommandError

from raw_materials.models import BatchMovement
from raw_materials.services.sync import sync_from_moysklad
from raw_materials.services.legacy_site_import import ImportBlocked, import_batches


class Command(BaseCommand):
    help = 'Перенести серии и сроки годности со старого сайта склада (файл базы warehouse.db)'

    def add_arguments(self, parser):
        parser.add_argument('db_path')

    def handle(self, *args, db_path, **options):
        sync_from_moysklad()
        try:
            report = import_batches(db_path)
        except ImportBlocked as error:
            raise CommandError(str(error))
        result = sync_from_moysklad(kind=BatchMovement.IMPORT)

        self.stdout.write(self.style.SUCCESS(f"Серий перенесено: {report['imported']}"))
        for name in sorted(set(report['unmatched'])):
            self.stdout.write(self.style.WARNING(f'Нет в МойСклад: {name}'))
        for line in report['unconverted']:
            self.stdout.write(self.style.WARNING(f'Единицы: {line}'))
        self.stdout.write(f"Сверка с МойСклад: поправлено сырья {result['corrected']} из {result['materials']}")
