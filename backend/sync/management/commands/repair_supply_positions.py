# sync/management/commands/repair_supply_positions.py
"""
Перечитать позиции приёмок, где сумма строк разошлась с суммой документа.

Зачем. До 10.09.2026 позиция приёмки искалась по паре «документ + материал»,
и один материал двумя строками (партию приняли двумя поставками) схлопывался
в одну: вторая строка перезаписывала первую. Сумма документа при этом
оставалась верной, а сумма строк — нет, и расхождение ничем себя не выдавало.
Замер 10.09.2026: 140 документов, 659 тыс. ₽.

Обычная синхронизация эти документы не тронет: она пропускает те, у которых
не менялась дата изменения в МойСкладе, а речь о документах 2024–2025 годов.
Поэтому здесь — точечно, по идентификатору, только расходящиеся.

    manage.py repair_supply_positions --dry-run   показать, что будет сделано
    manage.py repair_supply_positions             перечитать и переписать
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum

from core.models import RawMaterial, Supply, SupplyItem
from msapi import http as ms_http
from sync.moysklad import MoySkladAPIClient

# Меньше рубля — это округление копеек, а не потерянная строка.
THRESHOLD = Decimal('1')


class Command(BaseCommand):
    help = 'Перечитать позиции приёмок, где сумма строк разошлась с документом'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Показать расхождения и ничего не менять')
        parser.add_argument('--limit', type=int, default=0,
                            help='Взять не больше N документов (для пробы)')

    def handle(self, *args, **options):
        client = MoySkladAPIClient(settings.MOYSKLAD_TOKEN)
        diverging = self._diverging()
        if options['limit']:
            diverging = diverging[:options['limit']]

        if not diverging:
            self.stdout.write(self.style.SUCCESS('Расхождений нет'))
            return

        self.stdout.write(f'Документов с расхождением: {len(diverging)}')
        repaired = failed = 0
        recovered = Decimal('0')

        for supply, ours in diverging:
            # Позиции берём отдельным постраничным запросом, а не через expand.
            # Expand отдал бы до 1000 строк (проверено 10.09.2026), и сегодня
            # этого хватает с запасом — самая длинная приёмка 67 строк. Но ниже
            # мы удаляем все позиции документа и пишем заново, а по обрезанному
            # списку это стёрло бы остальное безвозвратно: здесь предпочитаю
            # лишний запрос молчаливой потере.
            positions = self._positions(client, supply)
            if positions is None:
                failed += 1
                continue
            if options['dry_run']:
                self.stdout.write(
                    f'  {supply.number} от {supply.date:%d.%m.%Y}: строк у нас '
                    f'{SupplyItem.objects.filter(supply=supply).count()}, в МойСкладе {len(positions)}, '
                    f'сумма {ours} против {supply.sum}')
                continue

            written = self._rewrite(supply, positions)
            if written is None:
                failed += 1
                continue
            repaired += 1
            recovered += written - ours

        if options['dry_run']:
            self.stdout.write('Ничего не изменено (--dry-run)')
            return

        self.stdout.write(self.style.SUCCESS(
            f'Перечитано документов: {repaired}, не удалось: {failed}, '
            f'вернулось в суммы строк: {recovered:.2f} ₽'))

    def _positions(self, client, supply):
        """Все позиции документа. None — если МойСклад не ответил."""
        rows, offset = [], 0
        while True:
            response = ms_http.get(
                f'{client.BASE_URL}/entity/supply/{supply.external_id}/positions',
                headers=client.headers,
                params={'expand': 'assortment', 'limit': 100, 'offset': offset}, timeout=60,
            )
            if response.status_code != 200:
                self.stdout.write(self.style.WARNING(
                    f'  {supply.number} от {supply.date:%d.%m.%Y}: МойСклад ответил {response.status_code}'))
                return None
            page = response.json().get('rows', [])
            rows.extend(page)
            if len(page) < 100:
                return rows
            offset += 100

    def _diverging(self):
        """Приёмки, где сумма строк отличается от суммы документа."""
        sums = {row['supply_id']: row['s']
                for row in SupplyItem.objects.values('supply_id').annotate(s=Sum('total'))}
        found = []
        for supply in Supply.objects.only('id', 'number', 'date', 'sum', 'external_id').iterator():
            ours = sums.get(supply.id)
            if ours is None or not supply.external_id:
                continue
            if abs(ours - supply.sum) >= THRESHOLD:
                found.append((supply, ours))
        return found

    def _rewrite(self, supply, positions):
        """Переписать материальные позиции документа целиком.

        Услуги («Доставка», «Комиссия») пропускаем: строка приёмки ссылается
        на материал, и хранить их нам сейчас негде. На такую сумму документ
        и останется расходиться — это граница модели, а не потерянная строка,
        и решать её отдельно.

        Товар, которого нет в базе, — другое дело: значит, не отработала
        синхронизация карточек, и переписывать документ вслепую нельзя.
        """
        rows = []
        skipped_services = Decimal('0')
        for position in positions:
            assortment = position.get('assortment') or {}
            kind = (assortment.get('meta') or {}).get('type', '')
            material = RawMaterial.objects.filter(external_id=assortment.get('id')).first()
            if not material and kind == 'service':
                skipped_services += (Decimal(str(position.get('price', 0))) / 100
                                     * Decimal(str(position.get('quantity', 0))))
                continue
            if not material:
                self.stdout.write(self.style.WARNING(
                    f'  {supply.number}: товара «{assortment.get("name", "?")}» нет в базе, документ пропущен'))
                return None
            quantity = Decimal(str(position.get('quantity', 0))).quantize(Decimal('0.001'))
            price = (Decimal(str(position.get('price', 0))) / 100).quantize(Decimal('0.000001'))
            rows.append(SupplyItem(
                supply=supply, raw_material=material, external_id=position.get('id'),
                quantity=quantity, price=price, total=(quantity * price).quantize(Decimal('0.01')),
            ))

        if not rows:
            # Ни одной материальной строки: документ целиком из услуг или
            # МойСклад отдал пусто. Стереть имеющиеся позиции и не записать
            # ничего — это потеря, а не починка.
            self.stdout.write(self.style.WARNING(
                f'  {supply.number}: материальных строк нет, документ не тронут'))
            return None

        with transaction.atomic():
            SupplyItem.objects.filter(supply=supply).delete()
            SupplyItem.objects.bulk_create(rows)

        if skipped_services:
            self.stdout.write(
                f'  {supply.number}: услуг на {skipped_services:.2f} ₽ не сохранено — хранить их негде')
        return sum((row.total for row in rows), Decimal('0'))
