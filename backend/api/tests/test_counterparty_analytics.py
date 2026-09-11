"""Категоризация контрагентов и детали группы: числа и цена расчёта.

Раньше и то и другое считалось обходом контрагентов, по несколько запросов на
каждого. Теперь это группировка в базе, а слияние старых карточек с основными
делается по карте, вычитанной одним запросом. Проверок нужно две: что слияние
осталось прежним и что число запросов не растёт вместе со справочником.
"""

import json
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import Counterparty, Product, Shipment, ShipmentItem
from forecasting.services.categorization.categorizer import CounterpartyCategorizator


class CategorizatorTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.product = Product.objects.create(
            name='Товар', external_id='p-1', group='Товары', subgroup='Био',
        )

    def ship(self, counterparty, days_ago, total):
        shipment = Shipment.objects.create(
            counterparty=counterparty,
            date=self.now - timedelta(days=days_ago),
            external_id=f'sh-{counterparty.id}-{days_ago}-{total}',
        )
        ShipmentItem.objects.create(
            shipment=shipment, product=self.product,
            quantity=Decimal('1'), price=Decimal(total),
        )

    def stats(self):
        return CounterpartyCategorizator().calculate_statistics()

    def test_legacy_card_reports_under_the_main_one(self):
        """Отгрузки старой карточки достаются основной, отдельной строки нет."""
        main = Counterparty.objects.create(name='Основной', external_id='c-1')
        legacy = Counterparty.objects.create(
            name='Основной (старый)', external_id='c-1-old',
            is_legacy=True, main_counterparty=main,
        )
        self.ship(main, 10, '100')
        self.ship(legacy, 40, '50')

        rows = self.stats()
        self.assertEqual(list(rows['counterparty_id']), [main.id])
        self.assertEqual(float(rows.iloc[0]['total_sum']), 150)
        self.assertEqual(int(rows.iloc[0]['total_months']), 2)

    def test_same_month_from_both_cards_stays_one_month(self):
        """Месяц, в котором отгружались обе карточки, остаётся одним месяцем."""
        main = Counterparty.objects.create(name='Основной', external_id='c-1')
        legacy = Counterparty.objects.create(
            name='Основной (старый)', external_id='c-1-old',
            is_legacy=True, main_counterparty=main,
        )
        self.ship(main, 2, '100')
        self.ship(legacy, 3, '50')

        row = self.stats().iloc[0]
        self.assertEqual(int(row['total_months']), 1)
        self.assertEqual(float(row['total_sum']), 150)

    def test_orphan_legacy_card_is_not_reported(self):
        """Старая карточка без основной не превращается в отдельного контрагента."""
        orphan = Counterparty.objects.create(
            name='Ничей (старый)', external_id='c-orphan', is_legacy=True,
        )
        self.ship(orphan, 5, '70')
        self.assertTrue(self.stats().empty)

    def test_counterparty_without_shipments_is_not_reported(self):
        """Контрагент без отгрузок в статистику не попадает — как и раньше."""
        Counterparty.objects.create(name='Молчун', external_id='c-quiet')
        self.assertTrue(self.stats().empty)

    def test_shipment_marked_as_missing_is_left_out(self):
        """Отгрузка, пропавшая из МойСклад, в статистику не идёт."""
        main = Counterparty.objects.create(name='Основной', external_id='c-1')
        self.ship(main, 10, '100')
        self.ship(main, 40, '50')

        gone = Shipment.all_objects.order_by('pk').first()
        gone.deleted_at = timezone.now()
        gone.save(update_fields=['deleted_at'])

        row = self.stats().iloc[0]
        self.assertEqual(float(row['total_sum']), 50)

    def test_broken_calculation_is_not_disguised_as_an_empty_report(self):
        """Поломка расчёта видна как ошибка, а не как раздел без данных."""
        with patch.object(
            ShipmentItem.objects, 'filter', side_effect=RuntimeError('база отвалилась')
        ):
            with self.assertRaisesMessage(RuntimeError, 'база отвалилась'):
                self.stats()

    def test_query_count_does_not_grow_with_the_directory(self):
        """Пять контрагентов и пятьдесят — одинаковое число запросов."""
        def queries_for(count):
            Counterparty.objects.all().delete()
            for index in range(count):
                counterparty = Counterparty.objects.create(
                    name=f'Контрагент {index}', external_id=f'c-{index}',
                )
                self.ship(counterparty, index + 1, '100')
            with CaptureQueriesContext(connection) as captured:
                self.stats()
            return len(captured)

        for_five, for_fifty = queries_for(5), queries_for(50)
        self.assertEqual(
            for_five, for_fifty,
            f'запросов на 5 контрагентов: {for_five}, на 50: {for_fifty}',
        )


class CounterpartyGroupDetailsTests(TestCase):
    """Помесячная динамика группы: сумма по всем её контрагентам."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user(username='groups', password='pass12345')
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(user)
        self.client.login(username='groups', password='pass12345')

        self.now = timezone.now()
        self.product = Product.objects.create(
            name='Товар', external_id='p-1', group='Товары', subgroup='Био',
        )
        for index in range(6):
            counterparty = Counterparty.objects.create(
                name=f'Контрагент {index}', external_id=f'c-{index}',
            )
            for days_ago in (5, 40):
                shipment = Shipment.objects.create(
                    counterparty=counterparty,
                    date=self.now - timedelta(days=days_ago),
                    external_id=f'sh-{index}-{days_ago}',
                )
                ShipmentItem.objects.create(
                    shipment=shipment, product=self.product,
                    quantity=Decimal('1'), price=Decimal('100') * (index + 1),
                )

    def _details(self, category):
        response = self.client.get(f'/api/counterparty-groups/{category}/')
        self.assertEqual(response.status_code, 200, category)
        return json.loads(response.content)['data']

    def _populated_categories(self):
        """Категории, в которые попал хоть кто-то: пороги считаются от данных."""
        found = []
        for category in CounterpartyCategorizator.CATEGORIES:
            response = self.client.get(f'/api/counterparty-groups/{category}/')
            if response.status_code == 200 and json.loads(response.content)['data']['counterparties']:
                found.append(category)
        self.assertTrue(found, 'ни в одну категорию никто не попал — данные теста бесполезны')
        return found

    def test_monthly_dynamics_sums_the_whole_group(self):
        """Динамика — сумма по всем контрагентам группы, помесячно."""
        total_by_month = defaultdict(float)
        for category in self._populated_categories():
            data = self._details(category)
            for point in data['monthly_dynamics']:
                total_by_month[point['month']] += point['value']

        # Шесть контрагентов, у каждого по отгрузке в двух месяцах на
        # 100·(номер+1): 2100 в каждом месяце.
        self.assertEqual(len(total_by_month), 2)
        for month, amount in total_by_month.items():
            self.assertEqual(amount, 2100, month)

    def test_query_count_does_not_grow_with_the_group(self):
        """Динамика считается одним запросом, а не запросом на контрагента."""
        category = self._populated_categories()[0]

        def queries_for(extra_counterparties):
            for index in range(extra_counterparties):
                counterparty = Counterparty.objects.create(
                    name=f'Добавочный {index}', external_id=f'extra-{index}',
                )
                shipment = Shipment.objects.create(
                    counterparty=counterparty, date=self.now - timedelta(days=5),
                    external_id=f'sh-extra-{index}',
                )
                ShipmentItem.objects.create(
                    shipment=shipment, product=self.product,
                    quantity=Decimal('1'), price=Decimal('100'),
                )
            with CaptureQueriesContext(connection) as captured:
                self.client.get(f'/api/counterparty-groups/{category}/')
            return len(captured)

        before = queries_for(0)
        after = queries_for(20)
        self.assertEqual(
            before, after,
            f'запросов было {before}, после двадцати новых контрагентов {after}',
        )
