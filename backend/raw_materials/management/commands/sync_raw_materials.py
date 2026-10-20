from django.core.management.base import BaseCommand

from raw_materials.services.sync import sync_from_moysklad


class Command(BaseCommand):
    help = 'Сверить остатки и серии склада сырья с МойСклад'

    def handle(self, *args, **options):
        result = sync_from_moysklad()
        self.stdout.write(self.style.SUCCESS(
            f"Сырья на складе: {result['materials']}, серии поправлены у {result['corrected']}, "
            f"пропущено на пересчёте в МойСклад: {result['skipped']}"
        ))
