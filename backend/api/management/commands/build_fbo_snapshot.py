# api/management/commands/build_fbo_snapshot.py
"""
Собрать снимок раздела «FBO Заказы» и положить его в базу.

Запускается по расписанию (реестр проверок, `horsebio_fbo_snapshot`) и кнопкой
«Обновить» на странице. Смысл тот же, что у уценки и остатков: МойСклад уходит
из запроса пользователя, а недоступность чужого API делает данные несвежими,
а не пустыми.
"""
from django.core.management.base import BaseCommand

from api.models import SectionSnapshot


class Command(BaseCommand):
    help = 'Пересобрать снимок раздела «FBO Заказы» из МойСклад'

    def handle(self, *args, **options):
        from api.views.fbo import SECTION_KEY, build_snapshot

        payload = build_snapshot()

        stats = payload.get('statistics') or {}
        self.stdout.write(self.style.SUCCESS(
            'Снимок собран: заказов за период {total}, из них FBO {fbo}, товаров {products}'.format(
                total=stats.get('total_orders', 0),
                fbo=stats.get('fbo_orders', 0),
                products=len(payload.get('products') or []),
            )
        ))
        stored = SectionSnapshot.stored(SECTION_KEY)
        self.stdout.write(f'Собран: {stored.updated_at:%d.%m.%Y %H:%M}')
