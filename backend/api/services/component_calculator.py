"""
Сервис расчёта компонентов для производства товаров.

Принимает список товаров с количеством и рассчитывает суммарное
количество компонентов (материалов), необходимых для производства.
"""
from decimal import Decimal
from typing import TypedDict
from collections import defaultdict
import pandas as pd
from io import BytesIO

from core.models import Product, ProcessingPlanProduct


class OrderItem(TypedDict):
    article: str
    name: str
    quantity: int


class ComponentResult(TypedDict):
    material_id: int
    material_name: str
    uom: str
    total_quantity: Decimal


class ProductResult(TypedDict):
    article: str
    name: str
    quantity: int
    found: bool
    has_processing_plan: bool  # есть ли техкарта
    processing_plan_name: str | None  # название техкарты
    components: list[dict]
    error: str | None


class CalculationResult(TypedDict):
    success: bool
    products: list[ProductResult]
    components_summary: list[ComponentResult]
    products_found: int
    products_not_found: int
    products_without_processing_plan: int  # товары без техкарт
    errors: list[str]


class ComponentCalculator:
    """Калькулятор компонентов для производства."""

    def parse_excel(self, file_content: bytes) -> list[OrderItem]:
        """
        Парсит Excel файл с заказом.

        Ожидаемые колонки:
        - Артикул
        - Наименование
        - Количество (любая колонка с числом)
        """
        df = pd.read_excel(BytesIO(file_content))

        # Ищем колонку с артикулом
        article_col = None
        for col in df.columns:
            if 'артикул' in col.lower():
                article_col = col
                break

        if not article_col:
            raise ValueError("Не найдена колонка 'Артикул'")

        # Ищем колонку с наименованием
        name_col = None
        for col in df.columns:
            if 'наименование' in col.lower():
                name_col = col
                break

        # Ищем колонку с количеством (третья колонка или с числами)
        quantity_col = None
        for col in df.columns:
            if col != article_col and col != name_col:
                # Проверяем, есть ли числа в колонке
                if pd.api.types.is_numeric_dtype(df[col]):
                    quantity_col = col
                    break

        if not quantity_col:
            raise ValueError("Не найдена колонка с количеством")

        items = []
        for _, row in df.iterrows():
            article = str(row[article_col]).strip() if pd.notna(row[article_col]) else ''
            name = str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else ''
            quantity = int(row[quantity_col]) if pd.notna(row[quantity_col]) else 0

            if article and quantity > 0:
                items.append({
                    'article': article,
                    'name': name,
                    'quantity': quantity
                })

        return items

    def calculate_for_product(self, article: str, quantity: int) -> ProductResult:
        """
        Рассчитывает компоненты для одного товара.

        Args:
            article: Артикул товара
            quantity: Необходимое количество товара

        Returns:
            ProductResult с информацией о товаре и его компонентах
        """
        result: ProductResult = {
            'article': article,
            'name': '',
            'quantity': quantity,
            'found': False,
            'has_processing_plan': False,
            'processing_plan_name': None,
            'components': [],
            'error': None
        }

        # Ищем товар по артикулу
        # Если есть несколько товаров с одним артикулом (дубликаты),
        # предпочитаем тот, у которого есть техкарта
        products = Product.objects.filter(article=article)
        if not products.exists():
            result['error'] = f"Товар с артикулом '{article}' не найден"
            return result

        # Ищем товар с техкартой среди дубликатов
        product = None
        plan_product = None
        for p in products:
            pp = ProcessingPlanProduct.objects.filter(product=p).first()
            if pp:
                product = p
                plan_product = pp
                break

        # Если ни у одного нет техкарты, берём первый
        if not product:
            product = products.first()

        result['found'] = True
        result['name'] = product.name

        # Проверяем техкарту
        if not plan_product:
            result['error'] = f"Техкарта для товара '{product.name}' не найдена"
            return result

        result['has_processing_plan'] = True
        result['processing_plan_name'] = plan_product.processing_plan.name

        # Рассчитываем количество техкарт
        # plan_product.quantity - сколько единиц продукта получается из 1 техкарты
        plan_output = plan_product.quantity
        if plan_output <= 0:
            result['error'] = f"Некорректный выход техкарты: {plan_output}"
            return result

        # Количество техкарт для производства
        plans_needed = Decimal(quantity) / plan_output

        # Получаем материалы техкарты
        for material in plan_product.processing_plan.materials.all():
            component_quantity = material.quantity * plans_needed
            result['components'].append({
                'material_id': material.material.id,
                'material_name': material.material.name,
                'uom': material.material.uom_name or 'шт',
                'quantity_per_recipe': float(material.quantity),
                'total_quantity': float(component_quantity)
            })

        return result

    def calculate(self, items: list[OrderItem]) -> CalculationResult:
        """
        Рассчитывает суммарные компоненты для списка товаров.

        Args:
            items: Список товаров с артикулами и количеством

        Returns:
            CalculationResult с детализацией по товарам и суммарными компонентами
        """
        result: CalculationResult = {
            'success': True,
            'products': [],
            'components_summary': [],
            'products_found': 0,
            'products_not_found': 0,
            'products_without_processing_plan': 0,
            'errors': []
        }

        # Агрегируем компоненты
        components_total: dict[int, dict] = defaultdict(lambda: {
            'material_id': 0,
            'material_name': '',
            'uom': '',
            'total_quantity': Decimal(0)
        })

        for item in items:
            product_result = self.calculate_for_product(
                article=item['article'],
                quantity=item['quantity']
            )
            result['products'].append(product_result)

            if not product_result['found']:
                result['products_not_found'] += 1
                result['errors'].append(product_result['error'])
            elif not product_result['has_processing_plan']:
                result['products_without_processing_plan'] += 1
                result['errors'].append(product_result['error'])
            else:
                result['products_found'] += 1

                # Суммируем компоненты
                for comp in product_result['components']:
                    mat_id = comp['material_id']
                    components_total[mat_id]['material_id'] = mat_id
                    components_total[mat_id]['material_name'] = comp['material_name']
                    components_total[mat_id]['uom'] = comp['uom']
                    components_total[mat_id]['total_quantity'] += Decimal(str(comp['total_quantity']))

        # Преобразуем в список и сортируем по имени
        result['components_summary'] = sorted(
            [
                {
                    'material_id': v['material_id'],
                    'material_name': v['material_name'],
                    'uom': v['uom'],
                    'total_quantity': float(v['total_quantity'])
                }
                for v in components_total.values()
            ],
            key=lambda x: x['material_name']
        )

        if result['products_not_found'] > 0 or result['products_without_processing_plan'] > 0:
            result['success'] = False

        return result

    def calculate_from_excel(self, file_content: bytes) -> CalculationResult:
        """
        Полный расчёт из Excel файла.

        Args:
            file_content: Содержимое Excel файла

        Returns:
            CalculationResult с детализацией и суммарными компонентами
        """
        items = self.parse_excel(file_content)
        return self.calculate(items)
