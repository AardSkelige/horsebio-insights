# api/test_purchase_analysis.py
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from core.models import (
    PurchaseOrder,
    PurchaseOrderItem,
    RawMaterial,
    Counterparty,
    Supply,
    Shipment,
    ShipmentItem,
    Product,
    RawMaterialUsage
)
from datetime import datetime, timedelta
from decimal import Decimal
import json


class PurchaseAnalysisTests(TestCase):
    def setUp(self):
        """Подготовка тестовых данных"""
        self.client = APIClient()

        # Создаем пользователя и авторизуемся
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        from api.access import grant_all_assignable_pages
        grant_all_assignable_pages(self.user)
        self.client.login(username='testuser', password='testpass123')

        # Создаем тестового поставщика
        self.supplier = Counterparty.objects.create(
            name="Test Supplier",
            external_id="TS1"
        )
        
        # Создаем тестовый материал
        self.material = RawMaterial.objects.create(
            name="Test Material",
            external_id="TM1",
            uom_name="шт",
            group="Материалы для производства"
        )
        
        # Создаем несколько заказов с разными датами
        self.create_test_orders()

    def create_test_orders(self):
        """Создание тестовых заказов"""
        current_date = timezone.now()
        
        # Создаем заказы за последние 3 месяца
        for month_offset in range(3):
            order_date = current_date - timedelta(days=30 * month_offset)
            supply_date = order_date + timedelta(days=5)  # Просто добавляем 5 дней
            
            # Создаем заказ
            order = PurchaseOrder.objects.create(
                external_id=f"PO{month_offset}",
                number=f"ORDER-{month_offset}",
                date=order_date,
                created=order_date,
                counterparty=self.supplier,
                status="completed",
                sum=Decimal("1000.00")
            )
            
            # Создаем связанную приемку
            supply = Supply.objects.create(
                external_id=f"S{month_offset}",
                number=f"SUPPLY-{month_offset}",
                date=supply_date,  # Используем дату с timezone
                counterparty=self.supplier,
                sum=Decimal("1000.00")
            )
            
            # Связываем заказ с приемкой
            order.supplies.add(supply)
            
            # Создаем позицию заказа
            PurchaseOrderItem.objects.create(
                purchase_order=order,
                raw_material=self.material,
                quantity=Decimal("10.00"),
                price=Decimal("100.00"),
                total=Decimal("1000.00"),
                shipped_quantity=Decimal("10.00")
            )

    def test_purchase_analysis_overview(self):
        """Тестирование endpoint'а общего анализа закупок"""
        url = reverse('api:purchase_analysis_overview')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем общую статистику
        self.assertEqual(data['total_statistics']['total_orders'], 3)
        self.assertEqual(data['total_statistics']['total_materials'], 1)
        self.assertEqual(data['total_statistics']['total_suppliers'], 1)
        
        # Проверяем анализ lead time
        self.assertIn('lead_time_analysis', data)
        self.assertEqual(data['lead_time_analysis']['avg'], 5)  # 5 дней
        
        # Проверяем топ материалов
        self.assertIn('top_materials', data)
        self.assertEqual(len(data['top_materials']), 1)
        self.assertEqual(data['top_materials'][0]['name'], 'Test Material')
        
        # Проверяем топ поставщиков
        self.assertIn('top_suppliers', data)
        self.assertEqual(len(data['top_suppliers']), 1)
        self.assertEqual(data['top_suppliers'][0]['name'], 'Test Supplier')
        
        # Проверяем помесячную динамику
        self.assertIn('monthly_dynamics', data)
        self.assertEqual(len(data['monthly_dynamics']), 3)

    def test_purchase_analysis_with_period(self):
        """Тестирование анализа с указанием периода"""
        end_date = timezone.now().strftime('%Y-%m-%d')
        url = reverse('api:purchase_analysis_overview')
        response = self.client.get(url, {
            'end_date': end_date,
            'period_months': 2
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        
        # Проверяем, что получили данные только за 2 месяца
        self.assertEqual(len(data['monthly_dynamics']), 2)

    def test_purchase_analysis_empty_data(self):
        """Тестирование анализа при отсутствии данных"""
        # Удаляем все тестовые данные
        PurchaseOrder.objects.all().delete()
        
        url = reverse('api:purchase_analysis_overview')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data['data']
        
        # Проверяем, что получаем нулевые значения
        self.assertEqual(data['total_statistics']['total_orders'], 0)
        self.assertEqual(data['total_statistics']['total_materials'], 0)
        self.assertEqual(len(data['monthly_dynamics']), 0)

    def test_material_purchase_analysis(self):
        """Тестирование endpoint'а анализа закупок конкретного материала"""
        url = reverse('api:material_purchase_analysis', args=[self.material.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')

        data = response.data['data']

        # Проверяем базовую информацию о материале
        self.assertIn('material', data)
        material_info = data['material']
        self.assertEqual(material_info['id'], self.material.id)
        self.assertEqual(material_info['name'], self.material.name)

        # Проверяем наличие основных секций ответа
        self.assertIn('suppliers', data)
        self.assertIn('recommendations', data)
        self.assertIn('general_calculations', data)
        self.assertIn('related_materials', data)

    def test_material_purchase_analysis_invalid_id(self):
        """Тестирование анализа с несуществующим ID материала"""
        invalid_id = 99999
        url = reverse('api:material_purchase_analysis', args=[invalid_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_material_purchase_analysis_with_period(self):
        """Тестирование анализа материала с указанием периода"""
        url = reverse('api:material_purchase_analysis', args=[self.material.id])
        end_date = timezone.now().strftime('%Y-%m-%d')

        response = self.client.get(url, {
            'end_date': end_date,
            'period_months': 2
        })

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')

        data = response.data['data']

        # Проверяем наличие основных секций ответа
        self.assertIn('material', data)
        self.assertIn('suppliers', data)
        self.assertIn('recommendations', data)

    def test_related_materials_analysis(self):
        """Тестирование endpoint'а анализа связанных материалов"""
        # Сначала создадим реальные связанные данные
        order = PurchaseOrder.objects.create(
            external_id="PO_TEST",
            number="ORDER-TEST",
            date=timezone.now(),
            created=timezone.now(),
            counterparty=self.supplier,
            status="completed",
            sum=Decimal("2000.00")
        )
        
        # Создаем связанный материал
        related_material = RawMaterial.objects.create(
            name="Related Material",
            external_id="RM1",
            uom_name="шт",
            group="Материалы для производства"
        )
        
        # Добавляем обе позиции в один заказ
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            raw_material=self.material,
            quantity=Decimal("10.00"),
            price=Decimal("100.00"),
            total=Decimal("1000.00"),
            shipped_quantity=Decimal("10.00")
        )
        
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            raw_material=related_material,
            quantity=Decimal("10.00"),
            price=Decimal("100.00"),
            total=Decimal("1000.00"),
            shipped_quantity=Decimal("10.00")
        )

        url = reverse('api:related_materials_analysis', args=[self.material.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем базовую структуру ответа
        self.assertIn('material_id', data)
        self.assertIn('period', data)
        self.assertIn('total_orders', data)
        self.assertIn('supplier_materials', data)
        
        # Проверяем информацию о периоде
        period = data['period']
        self.assertIn('start_date', period)
        self.assertIn('end_date', period)
        self.assertIn('months', period)
        
        # Проверяем данные поставщиков
        supplier_materials = data['supplier_materials']
        self.assertIn(self.supplier.name, supplier_materials)
        
        supplier_data = supplier_materials[self.supplier.name]
        self.assertIn('related', supplier_data)
        self.assertIn('skipped', supplier_data)
        self.assertIn('total_orders', supplier_data)
        
        # Проверяем наличие связанного материала
        related_items = supplier_data['related']
        self.assertTrue(len(related_items) > 0)
        self.assertEqual(related_items[0]['name'], "Related Material")

    def test_related_materials_analysis_invalid_id(self):
        """Тестирование анализа связанных материалов с несуществующим ID"""
        invalid_id = 99999
        url = reverse('api:related_materials_analysis', args=[invalid_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_related_materials_analysis_with_period(self):
        """Тестирование анализа связанных материалов с указанием периода"""
        url = reverse('api:related_materials_analysis', args=[self.material.id])
        end_date = timezone.now().strftime('%Y-%m-%d')
        
        response = self.client.get(url, {
            'end_date': end_date,
            'period_months': 2
        })
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем период
        self.assertEqual(data['period']['months'], 2)
        
        # Проверяем, что данные ограничены периодом
        # Количество заказов должно быть не больше 2 (за 2 месяца)
        supplier_data = data['supplier_materials'].get(self.supplier.name, {})
        self.assertLessEqual(supplier_data.get('total_orders', 0), 2)

    def test_related_materials_extended(self):
        """Расширенное тестирование анализа связанных материалов с дополнительными материалами"""
        # Создаем дополнительный материал
        related_material = RawMaterial.objects.create(
            name="Related Material",
            external_id="RM1",
            uom_name="шт",
            group="Материалы для производства"
        )
        
        # Создаем заказ с обоими материалами
        order = PurchaseOrder.objects.create(
            external_id="PO_RELATED",
            number="ORDER-RELATED",
            date=timezone.now(),
            created=timezone.now(),
            counterparty=self.supplier,
            status="completed",
            sum=Decimal("2000.00")
        )
        
        # Добавляем позиции заказа
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            raw_material=self.material,
            quantity=Decimal("10.00"),
            price=Decimal("100.00"),
            total=Decimal("1000.00"),
            shipped_quantity=Decimal("10.00")
        )
        
        PurchaseOrderItem.objects.create(
            purchase_order=order,
            raw_material=related_material,
            quantity=Decimal("10.00"),
            price=Decimal("100.00"),
            total=Decimal("1000.00"),
            shipped_quantity=Decimal("10.00")
        )
        
        url = reverse('api:related_materials_analysis', args=[self.material.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        supplier_materials = data['supplier_materials']
        
        # Проверяем, что связанный материал появился в результатах
        supplier_data = supplier_materials.get(self.supplier.name, {})
        related_materials = supplier_data.get('related', [])
        
        found_related = False
        for material in related_materials:
            if material['name'] == "Related Material":
                found_related = True
                self.assertIn('frequency', material)
                self.assertIn('joint_count', material)
                break
                
        self.assertTrue(found_related, "Related material should be found in the analysis")

    def test_optimize_purchase_points(self):
        """Тестирование endpoint'а оптимизации точек заказа"""
        url = reverse('api:optimize_purchase_points', args=[self.material.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем базовую структуру ответа
        self.assertIn('material', data)
        self.assertIn('period', data)
        self.assertIn('recommendations', data)
        self.assertIn('related_materials', data)
        
        # Проверяем информацию о материале
        material_info = data['material']
        self.assertEqual(material_info['id'], self.material.id)
        self.assertEqual(material_info['name'], self.material.name)
        self.assertEqual(material_info['uom'], self.material.uom_name)
        
        # Проверяем рекомендации
        recommendations = data['recommendations']
        self.assertTrue(isinstance(recommendations, list))
        
        if recommendations:  # Если есть рекомендации
            recommendation = recommendations[0]
            self.assertIn('supplier_name', recommendation)
            self.assertIn('reorder_point', recommendation)
            self.assertIn('optimal_batch', recommendation)
            self.assertIn('safety_stock', recommendation)
            self.assertIn('lead_time', recommendation)
            self.assertIn('reliability', recommendation)
            
            # Проверяем, что числовые значения имеют смысл
            self.assertGreaterEqual(recommendation['reorder_point'], 0)
            self.assertGreaterEqual(recommendation['optimal_batch'], 0)
            self.assertGreaterEqual(recommendation['safety_stock'], 0)
            self.assertGreaterEqual(recommendation['reliability'], 0)
            self.assertGreaterEqual(recommendation['lead_time'], 0)

    def test_optimize_purchase_points_with_params(self):
        """Тестирование оптимизации точек заказа с дополнительными параметрами"""
        # Создаем больше тестовых данных для расчета
        order_date = timezone.now() - timedelta(days=30)
        
        # Создаем несколько заказов и поставок
        for i in range(3):
            # Создаем заказ и поставку как раньше
            order = PurchaseOrder.objects.create(
                external_id=f"PO_SAFETY_{i}",
                number=f"ORDER-SAFETY-{i}",
                date=order_date + timedelta(days=i*10),
                created=order_date + timedelta(days=i*10),
                counterparty=self.supplier,
                status="completed",
                sum=Decimal("2000.00")
            )
            
            # Создаем связанную приемку
            supply = Supply.objects.create(
                external_id=f"S_SAFETY_{i}",
                number=f"SUPPLY-SAFETY-{i}",
                date=order_date + timedelta(days=i*10 + 5),  # +5 дней для lead time
                counterparty=self.supplier,
                sum=Decimal("2000.00")
            )
            
            order.supplies.add(supply)
            
            # Создаем позицию заказа
            PurchaseOrderItem.objects.create(
                purchase_order=order,
                raw_material=self.material,
                quantity=Decimal("100.00"),
                price=Decimal("20.00"),
                total=Decimal("2000.00"),
                shipped_quantity=Decimal("100.00")
            )
            
            # Создаем данные об использовании материала
            # Создаем отгрузку
            shipment = Shipment.objects.create(
                external_id=f"SH_SAFETY_{i}",
                number=f"SHIPMENT-SAFETY-{i}",
                date=order_date + timedelta(days=i*10),
                counterparty=self.supplier
            )
            
            # Создаем позицию отгрузки
            shipment_item = ShipmentItem.objects.create(
                shipment=shipment,
                product=Product.objects.create(
                    name=f"Test Product {i}",
                    external_id=f"TP{i}",
                    group="Товары"
                ),
                quantity=Decimal("10.00"),
                price=Decimal("100.00")
            )
            
            # Создаем запись об использовании материала
            RawMaterialUsage.objects.create(
                shipment_item=shipment_item,
                raw_material=self.material,
                quantity=Decimal("50.00")  # Использование материала
            )

        url = reverse('api:optimize_purchase_points', args=[self.material.id])
        
        # Тестируем с указанием параметров
        params = {
            'safety_stock_days': 30,  # Увеличенный страховой запас
            'period_months': 6,       # Меньший период анализа
            'end_date': timezone.now().strftime('%Y-%m-%d')
        }
        
        response = self.client.get(url, params)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем базовые параметры
        self.assertIn('parameters', data)
        self.assertEqual(data['parameters']['safety_stock_days'], 30)
        
        # Проверяем период
        period = data['period']
        self.assertEqual(period['months'], 6)
        
        # Проверяем статистику использования
        self.assertIn('usage_statistics', data)
        usage_stats = data['usage_statistics']
        self.assertGreater(usage_stats['total_usage'], 0, "Должно быть зафиксировано использование материала")
        
        # Проверяем рекомендации
        self.assertIn('recommendations', data)
        self.assertTrue(len(data['recommendations']) > 0, "Должны быть рекомендации")
        
        if data['recommendations']:
            recommendation = data['recommendations'][0]
            
            # Выводим отладочную информацию
            print("\nОтладочная информация:")
            print(f"Safety stock days: {data['parameters']['safety_stock_days']}")
            print(f"Total usage: {usage_stats['total_usage']}")
            print(f"Average daily usage: {usage_stats['avg_daily']}")
            print(f"Average monthly usage: {usage_stats['avg_monthly']}")
            print(f"Safety stock: {recommendation['safety_stock']}")
            print(f"Reorder point: {recommendation['reorder_point']}")
            print(f"Lead time: {recommendation['lead_time']}")
            
            # Проверяем значения
            self.assertGreater(recommendation['safety_stock'], 0, 
                            "Страховой запас должен быть больше 0")
    
    
    def test_optimize_purchase_points_invalid_id(self):
        """Тестирование оптимизации с несуществующим ID материала"""
        invalid_id = 99999
        url = reverse('api:optimize_purchase_points', args=[invalid_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_optimize_purchase_points_no_data(self):
        """Тестирование оптимизации при отсутствии данных о закупках"""
        # Создаем новый материал без истории закупок
        new_material = RawMaterial.objects.create(
            name="New Material",
            external_id="NM1",
            uom_name="шт",
            group="Материалы для производства"
        )
        
        url = reverse('api:optimize_purchase_points', args=[new_material.id])
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'success')
        
        data = response.data['data']
        
        # Проверяем, что рекомендации пустые или содержат базовые значения
        self.assertEqual(len(data['recommendations']), 0)