"""Раздел материалов: числа в таблице и цена, которой они достаются.

Показатели собираются двумя группировками — по одной на связь — и склеиваются
в Python. Проверять нужно и числа, и форму запроса.

Числа: агрегаты по двум разным связям легко размножить join'ом, и материал
с двумя поставками и тремя расходами покажет утроенную поставку — на глаз
в таблице такое не заметишь.

Форма: раздел уже дважды ломался об одно и то же. Сначала обходом материалов
циклом — запрос на строку. Потом коррелированными подзапросами: запрос
формально один, счётчик запросов доволен, а выполняется подзапрос заново для
каждого материала, и секунда превращается в полторы минуты. Поэтому кроме
счётчика есть проверка на саму форму SQL.
"""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import (
    Counterparty, Product, RawMaterial, RawMaterialUsage,
    Shipment, ShipmentItem, Supply, SupplyItem,
)


class MaterialListTests(TestCase):
    """Один материал, у которого есть и расход, и поставки от разных поставщиков."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user(username='materials', password='pass12345')
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(user)
        self.client.login(username='materials', password='pass12345')

        self.now = timezone.now()
        self.customer = Counterparty.objects.create(name='Покупатель', external_id='c-1')
        self.supplier_one = Counterparty.objects.create(name='Поставщик один', external_id='s-1')
        self.supplier_two = Counterparty.objects.create(name='Поставщик два', external_id='s-2')
        self.product = Product.objects.create(name='Товар', external_id='p-1', group='Товары')

        self.material = RawMaterial.objects.create(
            name='Флакон', external_id='m-1', group='Тара', uom_name='шт', code='К-1',
        )

        # Расход: три позиции в двух разных отгрузках.
        self.usage_total = Decimal('0')
        for index, days_ago in enumerate((1, 1, 5)):
            shipment = Shipment.objects.get_or_create(
                external_id=f'sh-{days_ago}',
                defaults={'counterparty': self.customer, 'date': self.now - timedelta(days=days_ago)},
            )[0]
            item = ShipmentItem.objects.create(
                shipment=shipment, product=self.product,
                quantity=Decimal('1'), price=Decimal('10'),
            )
            quantity = Decimal('2') + index
            RawMaterialUsage.objects.create(
                shipment_item=item, raw_material=self.material, quantity=quantity,
            )
            self.usage_total += quantity

        # Поставки: две, от двух разных поставщиков.
        self.supplied_total = Decimal('0')
        for index, supplier in enumerate((self.supplier_one, self.supplier_two)):
            supply = Supply.objects.create(
                counterparty=supplier, external_id=f'sup-{index}',
                date=self.now - timedelta(days=3), number=f'П-{index}', sum=Decimal('100'),
            )
            quantity = Decimal('50') + index
            SupplyItem.objects.create(
                supply=supply, raw_material=self.material,
                quantity=quantity, price=Decimal('1'),
            )
            self.supplied_total += quantity

    def rows(self, query=''):
        response = self.client.get(f'/api/materials/{query}')
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertEqual(payload['status'], 'success')
        return payload['data']

    def test_usage_is_not_multiplied_by_the_number_of_supplies(self):
        """Расход считается по расходу, а не по его произведению с поставками."""
        row = self.rows()['materials'][0]
        self.assertEqual(Decimal(str(row['total_usage'])), self.usage_total)

    def test_shipments_and_suppliers_are_counted_distinctly(self):
        """Три позиции в двух отгрузках — это две отгрузки, а не три."""
        row = self.rows()['materials'][0]
        self.assertEqual(row['shipments_count'], 2)
        self.assertEqual(row['suppliers_count'], 2)

    def test_narrowing_by_supplier_switches_the_column_to_supplied(self):
        """Сужение по поставщику показывает поставленное, а не израсходованное."""
        data = self.rows(f'?counterparties={self.supplier_one.id}')
        row = data['materials'][0]
        self.assertEqual(Decimal(str(row['total_usage'])), Decimal('50'))
        self.assertEqual(row['suppliers_count'], 1)

    def test_dates_narrow_the_usage(self):
        """Период отсекает расход по дате отгрузки."""
        recent = (self.now - timedelta(days=2)).date().isoformat()
        row = self.rows(f'?startDate={recent}')['materials'][0]
        # За период остались только две позиции однодневной давности: 2 + 3.
        self.assertEqual(row['shipments_count'], 1)

    def test_material_without_movements_shows_zeroes(self):
        """Материал без расхода и поставок не выпадает из таблицы и не даёт None."""
        RawMaterial.objects.create(
            name='Этикетка', external_id='m-2', group='Этикетки', uom_name='шт',
        )
        rows = {row['name']: row for row in self.rows()['materials']}
        self.assertEqual(rows['Этикетка']['total_usage'], 0)
        self.assertEqual(rows['Этикетка']['shipments_count'], 0)
        self.assertEqual(rows['Этикетка']['suppliers_count'], 0)


class MaterialListOrderingTests(TestCase):
    """Порядок строк: точное совпадение, затем группа, затем колонка."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user(username='ordering', password='pass12345')
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(user)
        self.client.login(username='ordering', password='pass12345')

        for index, (name, group) in enumerate((
            ('Пробка', 'Тара'),
            ('Субстанция', 'Материалы для производства'),
            ('Этикетка малая', 'Этикетки'),
            ('Пробка резиновая', 'Тара'),
        )):
            RawMaterial.objects.create(
                name=name, external_id=f'm-{index}', group=group, uom_name='шт',
            )

    def names(self, query=''):
        response = self.client.get(f'/api/materials/{query}')
        self.assertEqual(response.status_code, 200)
        return [row['name'] for row in json.loads(response.content)['data']['materials']]

    def test_groups_keep_their_priority(self):
        """Производство впереди тары, тара впереди этикеток."""
        self.assertEqual(
            self.names(),
            ['Субстанция', 'Пробка', 'Пробка резиновая', 'Этикетка малая'],
        )

    def test_text_column_respects_the_direction(self):
        """Клик по текстовой колонке второй раз переворачивает порядок."""
        ascending = self.names('?sortField=name&sortOrder=asc')
        descending = self.names('?sortField=name&sortOrder=desc')
        # Приоритет групп сильнее колонки, поэтому переворачивается порядок
        # внутри группы, а не весь список.
        self.assertEqual(ascending, ['Субстанция', 'Пробка', 'Пробка резиновая', 'Этикетка малая'])
        self.assertEqual(descending, ['Субстанция', 'Пробка резиновая', 'Пробка', 'Этикетка малая'])

    def test_call_without_parameters_is_alphabetical(self):
        """Подбор материала в закупках зовёт список без сортировки — ждём алфавит."""
        self.assertEqual(self.names(), self.names('?sortField=name&sortOrder=asc'))

    def test_exact_name_match_comes_first(self):
        """Точное совпадение с поиском обгоняет даже приоритет группы."""
        self.assertEqual(self.names('?search=Пробка')[0], 'Пробка')

    def test_pagination_reports_the_full_count(self):
        """Страница отдаёт свой размер, а total считает всю выборку."""
        data = json.loads(self.client.get('/api/materials/?pageSize=2').content)['data']
        self.assertEqual(len(data['materials']), 2)
        self.assertEqual(data['total'], 4)

    def test_paging_does_not_repeat_or_lose_rows(self):
        """Строки без различий по сортировке не перескакивают между страницами."""
        first = self.names('?pageSize=2&page=1')
        second = self.names('?pageSize=2&page=2')
        self.assertEqual(len(set(first + second)), 4)


class MaterialListQueryCountTests(TestCase):
    """Цена страницы не должна расти вместе со справочником."""

    def setUp(self):
        self.client = Client()
        user = User.objects.create_user(username='counting', password='pass12345')
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(user)
        self.client.login(username='counting', password='pass12345')

    def create_materials(self, count):
        for index in range(count):
            RawMaterial.objects.create(
                name=f'Материал {index}', external_id=f'bulk-{index}',
                group='Тара', uom_name='шт',
            )

    def queries_for(self, material_count):
        RawMaterial.objects.all().delete()
        self.create_materials(material_count)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/api/materials/?pageSize=10')
            self.assertEqual(response.status_code, 200)
        return len(captured)

    def test_aggregates_are_flat_not_correlated(self):
        """Расход считается группировкой, а не подзапросом на каждый материал.

        Счётчика запросов тут мало: коррелированный подзапрос — это один
        запрос, и прошлая версия раздела проходила проверку на счёт, а на
        проде отвечала полторы минуты вместо секунды. Отличить их можно по
        форме SQL: в коррелированном варианте расход и справочник материалов
        оказываются в одном запросе, потому что подзапрос ссылается на
        строку внешней выборки.
        """
        self.create_materials(20)
        with CaptureQueriesContext(connection) as captured:
            response = self.client.get('/api/materials/?pageSize=10')
            self.assertEqual(response.status_code, 200)

        both = [
            query['sql'] for query in captured
            if 'parser_rawmaterialusage' in query['sql']
            and 'parser_rawmaterial"' in query['sql']
        ]
        self.assertEqual(
            both, [],
            'расход и справочник материалов попали в один запрос — '
            'подзапрос снова считается для каждой строки',
        )

    def test_query_count_does_not_grow_with_the_catalogue(self):
        """Десять материалов и сто — одинаковое число запросов."""
        for_ten = self.queries_for(10)
        for_hundred = self.queries_for(100)
        self.assertEqual(
            for_ten, for_hundred,
            f'запросов на 10 материалов: {for_ten}, на 100: {for_hundred} — '
            'страница снова ходит в базу за каждой строкой',
        )
