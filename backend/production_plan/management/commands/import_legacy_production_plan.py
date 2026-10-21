import sqlite3

from django.core.management.base import BaseCommand

from production_plan.models import Exclusion, GreenItem
from production_plan.services.articles import normalize

LEGACY_WORDS = ['мармелад', 'утг', 'старое', 'леденец']


class Command(BaseCommand):
    help = 'Перенести исключения и зелёный список производственного плана со старого сайта склада (warehouse.db)'

    def add_arguments(self, parser):
        parser.add_argument('db_path')

    def handle(self, *args, db_path, **options):
        db = sqlite3.connect(db_path)
        rules = [(word, '') for word in LEGACY_WORDS] + [
            (article, phrase) if article.strip() else (phrase, '')
            for phrase, article in db.execute('SELECT phrase, article FROM production_plan_exclusions')
        ]
        for text, note in rules:
            Exclusion.objects.update_or_create(text=' '.join(text.split()), defaults={'note': ' '.join(note.split())})
        for article, name in db.execute('SELECT article, product_name FROM production_green_list'):
            GreenItem.objects.update_or_create(article=normalize(article), defaults={'name': name or ''})
        self.stdout.write(self.style.SUCCESS(
            f'Исключений: {Exclusion.objects.count()}, зелёный список: {GreenItem.objects.count()}'
        ))
