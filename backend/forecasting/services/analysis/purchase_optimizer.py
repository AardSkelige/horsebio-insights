# Запуск тестового расчета оптимизации закупок
# python manage.py test_material_consumption --material-id=28

from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import math
from django.utils import timezone
from django.db.models import Avg, Count, Min, Max
from core.models import PurchaseOrder, Supply, RawMaterial, PurchaseOrderItem, SupplyItem
from forecasting.services.analysis.seasonal_demand_analyzer import SeasonalDemandAnalyzer
from core.models import RawMaterialUsage

import logging
logger = logging.getLogger(__name__)

# Feature flag for trend detection
# If True: uses recent 3-month average when growth trend detected (2 of 3 months > 1.3x yearly avg)
# If False: always uses yearly average (original behavior)
ENABLE_TREND_DETECTION = True

@dataclass
class OrderHistory:
    quantity: float
    lead_time: float
    date: str
    price: float
    supplier_name: str = None  # Добавляем поле с значением по умолчанию None


class PurchaseOptimizationCalculator:
    def __init__(
        self,
        orders: List[OrderHistory],
        material_id: int,
        holding_cost_percent: float = 0.15,  # Средний процент затрат на хранение (включает стоимость складского хранения, обслуживания, риски порчи и т.д.)
        ordering_cost: float = 1000,  # Стоимость размещения заказа (включает затраты на оформление, приемку и документооборот)
    ):
        self.orders = orders
        self.material_id = material_id
        self.holding_cost_percent = holding_cost_percent
        self.ordering_cost = ordering_cost
        self.seasonal_analyzer = SeasonalDemandAnalyzer(
            start_date=timezone.now() - timedelta(days=365),
            end_date=timezone.now()
        )
        # Инициализируем общие данные о потреблении
        self.total_consumption = self.calculate_total_material_consumption()
        
    def calculate_total_material_consumption(self):
        """Расчет общего среднего потребления"""
        try:
            # Получаем историю использования материала за последний год
            one_year_ago = timezone.now() - timedelta(days=365)
            
            usages = RawMaterialUsage.objects.filter(
                raw_material_id=self.material_id,
                shipment_item__shipment__date__gte=one_year_ago
            ).select_related(
                'shipment_item__shipment'
            )

            if not usages:
                # Нет данных об использовании материала
                no_data_reason = self._get_no_data_reason()
                return {
                    "value": self._calculate_average_from_orders(),
                    "details": no_data_reason
                }

            # Группируем использование по дням
            daily_usage = {}
            total_quantity = 0
            all_quantities = []

            for usage in usages:
                date = usage.shipment_item.shipment.date.date()
                quantity = float(usage.quantity)
                
                if date not in daily_usage:
                    daily_usage[date] = 0
                daily_usage[date] += quantity
                total_quantity += quantity
                all_quantities.append(daily_usage[date])

            # Определяем период
            dates = sorted(daily_usage.keys())
            if not dates:
                # Нет данных за последний год
                return {
                    "value": self._calculate_average_from_orders(),
                    "details": "Нет данных об использовании материала за последний год"
                }
                
            first_date = dates[0]
            last_date = dates[-1]
            
            # Считаем рабочие дни (пн-сб)
            working_days = self._calculate_working_days(first_date, last_date)

            if working_days == 0:
                # Период анализа некорректен
                return {
                    "value": self._calculate_average_from_orders(),
                    "details": "Некорректный период анализа"
                }

            # Рассчитываем статистики
            yearly_avg_daily = total_quantity / working_days

            # Сортируем количества для расчета медианы
            all_quantities.sort()
            median_daily = all_quantities[len(all_quantities)//2] if all_quantities else 0

            # Определяем максимальное дневное потребление
            max_daily = max(daily_usage.values()) if daily_usage else 0

            # === TREND DETECTION ===
            # Check if recent 3 months show growth trend
            trend_detected = False
            recent_avg_daily = None
            growth_ratio = None
            final_avg_daily = yearly_avg_daily
            trend_details = ""

            if ENABLE_TREND_DETECTION:
                three_months_ago = timezone.now() - timedelta(days=90)

                # Group usage by month for trend analysis
                monthly_usage = {}
                for date, qty in daily_usage.items():
                    month_key = date.strftime('%Y-%m')
                    if month_key not in monthly_usage:
                        monthly_usage[month_key] = 0
                    monthly_usage[month_key] += qty

                if monthly_usage:
                    # Calculate yearly monthly average
                    yearly_monthly_avg = sum(monthly_usage.values()) / len(monthly_usage)

                    # Get recent 3 months
                    sorted_months = sorted(monthly_usage.keys())
                    recent_months = sorted_months[-3:] if len(sorted_months) >= 3 else sorted_months

                    # Count months above 1.3x threshold
                    months_above_threshold = 0
                    for month in recent_months:
                        if monthly_usage.get(month, 0) > yearly_monthly_avg * 1.3:
                            months_above_threshold += 1

                    # Calculate recent average
                    recent_total = sum(monthly_usage.get(m, 0) for m in recent_months)
                    recent_monthly_avg = recent_total / len(recent_months) if recent_months else 0

                    # Calculate growth ratio
                    if yearly_monthly_avg > 0:
                        growth_ratio = recent_monthly_avg / yearly_monthly_avg

                    # Trigger condition: at least 2 of last 3 months > 1.3x yearly average
                    if months_above_threshold >= 2 and len(recent_months) >= 2:
                        trend_detected = True

                        # Calculate recent daily average from recent 3 months data
                        recent_dates = {d: q for d, q in daily_usage.items()
                                       if d >= three_months_ago.date()}
                        if recent_dates:
                            recent_working_days = self._calculate_working_days(
                                min(recent_dates.keys()),
                                max(recent_dates.keys())
                            )
                            if recent_working_days > 0:
                                recent_avg_daily = sum(recent_dates.values()) / recent_working_days
                                final_avg_daily = recent_avg_daily

                                trend_details = f"""

                ⚠️ ВЫЯВЛЕН РОСТ СПРОСА:
                - Годовое среднее: {yearly_avg_daily:.2f} ед./день ({yearly_avg_daily * 30:.2f} ед./мес)
                - Среднее за 3 месяца: {recent_avg_daily:.2f} ед./день ({recent_avg_daily * 30:.2f} ед./мес)
                - Коэффициент роста: {growth_ratio:.2f}x
                - Месяцев выше порога (1.3x): {months_above_threshold} из {len(recent_months)}

                → Расчёт выполнен по данным последних 3 месяцев
                """

            return {
                "value": final_avg_daily,
                "first_date": first_date,
                "last_date": last_date,
                "working_days": working_days,
                "active_days": len(daily_usage),
                "total_quantity": total_quantity,
                "max_daily": max_daily,
                "median_daily": median_daily,
                # Trend detection fields
                "trend_detected": trend_detected,
                "yearly_avg": yearly_avg_daily,
                "recent_avg": recent_avg_daily,
                "growth_ratio": growth_ratio,
                "details": f"""
                Расчет общего среднего потребления:

                Период анализа: {first_date.strftime('%d.%m.%Y')} - {last_date.strftime('%d.%m.%Y')}
                Всего рабочих дней (пн-сб): {working_days}
                Дней с использованием: {len(daily_usage)}
                Всего использовано: {total_quantity:.2f} ед.

                Потребление:
                - Среднее в рабочий день: {final_avg_daily:.2f} ед.
                - Медианное за день: {median_daily:.2f} ед.
                - Максимальное за день: {max_daily:.2f} ед.
                {trend_details}
                На основе фактического использования в производстве
                """
            }

        except Exception as e:
            # Логируем ошибку и возвращаем среднее из заказов
            logger.error(f"Error calculating material consumption: {str(e)}")
            return {
                "value": self._calculate_average_from_orders(),
                "details": f"Ошибка расчета: {str(e)}"
            }

    def _calculate_working_days(self, start_date, end_date):
        """Расчет рабочих дней с учетом 6-дневной рабочей недели и праздников"""
        HOLIDAYS_2025 = {  # Праздничные дни РФ на 2025 год
            (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7), (1, 8),
            (2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)
        }
        
        working_days = 0
        current_date = start_date
        while current_date <= end_date:
            # Проверяем является ли день рабочим (пн-сб)
            if current_date.weekday() < 6:  # 0-5 это пн-сб
                # Проверяем не является ли день праздником
                if (current_date.month, current_date.day) not in HOLIDAYS_2025:
                    working_days += 1
            current_date += timedelta(days=1)
        
        return working_days
    def _get_no_data_reason(self):
        """Определение причины отсутствия данных"""
        one_year_ago = timezone.now() - timedelta(days=365)
        
        orders = get_material_order_history(self.material_id)
        if not orders:
            # Проверяем историческое использование
            usage_exists = RawMaterialUsage.objects.filter(
                raw_material_id=self.material_id,
                shipment_item__shipment__date__gte=one_year_ago
            ).exists()
            
            if usage_exists:
                return """
                Материал используется в производстве (среднее {:.2f} ед. в день),
                но нет заказов за последний год.
                Рекомендуется проверить источники поставок.
                """.format(self.calculate_total_material_consumption()["value"])
            
            return "Нет данных о заказах и использовании материала за последний год"
        
        return "Нет данных об использовании материала в производстве при наличии заказов"
    
    def _calculate_average_from_orders(self):
        """Резервный метод расчета среднего на основе заказов"""
        if not self.orders:
            return 0
            
        total_ordered = sum(order.quantity for order in self.orders)
        oldest_order = min(self.orders, key=lambda x: datetime.fromisoformat(x.date))
        newest_order = max(self.orders, key=lambda x: datetime.fromisoformat(x.date))
        
        days_between = (datetime.fromisoformat(newest_order.date) - datetime.fromisoformat(oldest_order.date)).days + 1
        if days_between < 1:
            days_between = 1
            
        return total_ordered / days_between
    
    def calculate_supplier_orders(self, supplier_name: str) -> List[OrderHistory]:
        """Получение заказов для конкретного поставщика"""
        return [order for order in self.orders if order.supplier_name == supplier_name]
    
    def calculate_avg_daily_demand(self) -> Dict:
        """Этот метод теперь возвращает общее потребление"""
        return self.total_consumption

    def calculate_demand_stddev(self, avg_daily_demand: float) -> Dict:
        """Расчет стандартного отклонения спроса"""
        if not self.orders:
            return {"value": 0, "details": "Нет данных о заказах"}
            
        squared_diff_sum = sum(
            (order.quantity - avg_daily_demand) ** 2 
            for order in self.orders
        )
        n = len(self.orders)
        stddev = math.sqrt(squared_diff_sum / (n - 1)) if n > 1 else 0
        
        return {
            "value": stddev,
            "details": f"""
            Расчет стандартного отклонения:
            Сумма квадратов отклонений: {squared_diff_sum:.2f}
            Количество наблюдений: {n}
            Стандартное отклонение = √({squared_diff_sum:.2f} / {n-1}) = {stddev:.2f}
            """
        }

    def calculate_lead_time_stats(self) -> Dict:
        """Расчет статистики времени поставки"""
        if not self.orders:
            return {
                "avg": 0,
                "stddev": 0,
                "details": "Нет данных о заказах"
            }
            
        lead_times = [order.lead_time for order in self.orders]
        avg_lead_time = sum(lead_times) / len(lead_times)
        
        squared_diff_sum = sum(
            (lt - avg_lead_time) ** 2 
            for lt in lead_times
        )
        n = len(lead_times)
        lead_time_stddev = math.sqrt(squared_diff_sum / (n - 1)) if n > 1 else 0
        
        return {
            "avg": avg_lead_time,
            "stddev": lead_time_stddev,
            "details": f"""
            Расчет параметров времени поставки:
            Среднее время поставки = {avg_lead_time:.2f} дней
            Стандартное отклонение = {lead_time_stddev:.2f} дней
            На основе {n} поставок
            """
        }

    def calculate_reorder_point(self) -> Dict:
        """Расчет точки заказа"""
        daily_consumption = self.total_consumption 
        lead_time_stats = self.calculate_lead_time_stats()
        
        # Базовая точка заказа - запас на время поставки
        avg_lead_time = lead_time_stats["avg"]
        base_rop = daily_consumption["value"] * avg_lead_time
        
        # Страховой запас зависит от поставщика
        supplier_orders = [order.quantity for order in self.orders]
        avg_order_size = sum(supplier_orders) / len(supplier_orders) if supplier_orders else 0
        
        # Увеличиваем страховой запас с учетом вариации времени поставки
        safety_stock = max(
            avg_order_size,  # Минимум средний заказ
            daily_consumption["value"] * lead_time_stats["stddev"]  # Запас на вариацию lead time
        )
        
        reorder_point = base_rop + safety_stock
        
        return {
            "value": reorder_point,
            "details": f"""
            РАСЧЕТ СРЕДНЕГО ПОТРЕБЛЕНИЯ:
            {daily_consumption['details']}
            
            РАСЧЕТ СРЕДНЕГО ВРЕМЕНИ ПОСТАВКИ:
            {lead_time_stats['details']}
            
            РАСЧЕТ ТОЧКИ ЗАКАЗА (когда нужно делать новый заказ):
            
            1. Базовый запас на время поставки:
            Общее среднее потребление в день ({daily_consumption["value"]:.2f}) × 
            Среднее время поставки ({avg_lead_time:.1f} дн) = {base_rop:.2f}
            
            2. Страховой запас (больший из):
            - Средний объем заказа у поставщика: {avg_order_size:.2f}
            - Запас на вариацию сроков поставки: {daily_consumption["value"] * lead_time_stats["stddev"]:.2f}
            Выбрано: {safety_stock:.2f}
            
            Итоговая точка заказа = {base_rop:.2f} + {safety_stock:.2f} = {reorder_point:.2f}
            
            Это значит: новый заказ нужно делать, когда остаток на складе достигнет {reorder_point:.2f}
            """
        }
    def calculate_optimal_order_quantity(self) -> Dict:
        """Расчет оптимального размера заказа (EOQ)"""
        if not self.orders:
            return {"value": 0, "details": "Нет данных о заказах"}
            
        # Получаем среднее дневное потребление
        daily_consumption = self.total_consumption["value"]
        
        # Рассчитываем годовой спрос на основе рабочих дней
        working_days_per_year = self._calculate_working_days(
            timezone.now().replace(month=1, day=1),
            timezone.now().replace(month=12, day=31)
        )
        annual_demand = daily_consumption * working_days_per_year
        
        # Расчет средней цены единицы товара
        avg_price = sum(order.price for order in self.orders) / len(self.orders)
        
        # Затраты на хранение единицы товара в год (15% - средний показатель затрат на хранение)
        holding_cost = avg_price * self.holding_cost_percent
        
        # Формула EOQ = sqrt((2 * годовой_спрос * стоимость_заказа) / затраты_на_хранение)
        eoq = math.sqrt(
            (2 * annual_demand * self.ordering_cost) / holding_cost
        )
        
        return {
            "value": eoq,
            "details": f"""
            Расчет оптимального размера заказа (EOQ):

            1. Исходные данные:
            - Годовой спрос (D) = {daily_consumption:.2f} * {working_days_per_year} = {annual_demand:.2f}
            - Стоимость заказа (S) = {self.ordering_cost:.2f} (включает затраты на оформление, приемку и документооборот)
            - Средняя цена единицы = {avg_price:.2f}
            - Затраты на хранение (H) = {avg_price:.2f} * {self.holding_cost_percent} = {holding_cost:.2f}
            (15% - средний процент, включающий стоимость хранения на складе, обслуживание запасов и др.)

            2. Формула EOQ = √((2 * D * S) / H)
            EOQ = √((2 * {annual_demand:.2f} * {self.ordering_cost:.2f}) / {holding_cost:.2f})
            EOQ = {eoq:.2f}
            """
        }
    def calculate_safety_stock(self) -> Dict:
        """Расчет страхового запаса"""
        try:
            daily_consumption = Decimal(str(self.total_consumption["value"]))
            lead_time_stats = self.calculate_lead_time_stats()
            
            # Используем только стандартное отклонение времени поставки
            stddev = Decimal(str(lead_time_stats["stddev"]))
            
            # Расчет страхового запаса
            safety_stock = daily_consumption * stddev
                
            return {
                "value": safety_stock,
                "details": f"""
                Расчет страхового запаса:
                
                1. Базовые параметры:
                • Среднее потребление в день: {float(daily_consumption):.2f}
                • Стандартное отклонение времени поставки: {float(stddev):.2f}
                
                2. Формула расчета:
                Страховой запас = Дневное потребление × Стандартное отклонение времени поставки
                
                3. Расчет:
                {float(daily_consumption):.2f} × {float(stddev):.2f} = {float(safety_stock):.2f}
                """
            }
                
        except Exception as e:
            logger.error(f"Error calculating safety stock: {str(e)}")
            return {"value": 0, "details": "Ошибка расчета страхового запаса"}
    
    def calculate_periodic_orders(self) -> Dict:
        """Расчет заказов для разных периодов"""
        try:
            if not self.orders:
                logger.debug("No orders found in calculate_periodic_orders")
                return {"error": "Нет данных о заказах"}

            # Преобразуем все входные данные в Decimal
            daily_consumption = Decimal(str(self.total_consumption["value"]))
            monthly_consumption = daily_consumption * Decimal('30')
            quarterly_consumption = monthly_consumption * Decimal('3')

            lead_time_stats = self.calculate_lead_time_stats()
            avg_lead_time = Decimal(str(lead_time_stats["avg"]))
            
            # Получаем базовый страховой запас
            safety_stock = self.calculate_safety_stock()
            base_safety_stock = Decimal(str(safety_stock["value"]))
            
            # Для ежемесячных заказов
            monthly_order = {
                "order_size": float(monthly_consumption),  # Преобразуем обратно в float для JSON
                "safety_stock": float(base_safety_stock),
                "total_size": float(monthly_consumption + base_safety_stock),
                "frequency": "Ежемесячно",
                "details": f"""
                РАСЧЕТ РАЗМЕРА ЕЖЕМЕСЯЧНОГО ЗАКАЗА:

                1. Базовое потребление:
                • Среднее потребление в день: {float(daily_consumption):.2f} ед.
                • Количество дней в месяце: 30 дней
                • Месячное потребление: {float(monthly_consumption):.2f} ед.

                2. Страховой запас: {float(base_safety_stock):.2f} ед.
                Рассчитан с учетом:
                • Среднего времени поставки: {float(avg_lead_time):.1f} дней
                • Вариации в сроках поставок
                • Вариации в ежедневном потреблении
                
                3. Итоговый размер заказа:
                • Месячное потребление: {float(monthly_consumption):.2f} ед.
                • Страховой запас: {float(base_safety_stock):.2f} ед.
                • ИТОГО: {float(monthly_consumption + base_safety_stock):.2f} ед.
                """
            }

            # Для квартальных заказов увеличиваем страховой запас на 50%
            quarterly_safety_stock = base_safety_stock * Decimal('1.5')
            
            quarterly_order = {
                "order_size": float(quarterly_consumption),
                "safety_stock": float(quarterly_safety_stock),
                "total_size": float(quarterly_consumption + quarterly_safety_stock),
                "frequency": "Ежеквартально",
                "details": f"""
                РАСЧЕТ РАЗМЕРА КВАРТАЛЬНОГО ЗАКАЗА:

                1. Базовое потребление:
                • Месячное потребление: {float(monthly_consumption):.2f} ед.
                • Количество месяцев: 3
                • Квартальное потребление: {float(quarterly_consumption):.2f} ед.
                
                2. Увеличенный страховой запас:
                • Базовый страховой запас: {float(base_safety_stock):.2f} ед.
                • Коэффициент увеличения: 1.5 (на 50% больше)
                • Увеличенный страховой запас: {float(quarterly_safety_stock):.2f} ед.
                
                Страховой запас увеличен из-за:
                - Большего периода между поставками
                - Большего риска задержек
                - Большей неопределенности в потреблении
                
                3. Итоговый размер заказа:
                • Квартальное потребление: {float(quarterly_consumption):.2f} ед.
                • Увеличенный страховой запас: {float(quarterly_safety_stock):.2f} ед.
                • ИТОГО: {float(quarterly_consumption + quarterly_safety_stock):.2f} ед.
                """
            }

            # Анализ сезонности
            try:
                seasonal_data = self.seasonal_analyzer.analyze_seasonality_pattern(
                    self.seasonal_analyzer.get_sales_history(self.material_id)
                )
                
                current_month = timezone.now().month
                
                if 'error' in seasonal_data:
                    seasonality_info = {
                        "type": "NO_SEASONALITY",
                        "current_factor": 1.0,
                        "recommendation": f"""
                        Анализ сезонности:
                        {seasonal_data['error']}
                        
                        Рекомендация: использовать стандартный размер заказа
                        """
                    }
                else:
                    seasonal_factor = seasonal_data.get('seasonal_factors', {}).get(current_month, 1.0)
                    seasonality_info = {
                        "type": seasonal_data.get('seasonality_type', 'NO_SEASONALITY'),
                        "current_factor": seasonal_factor,
                        "recommendation": f"""
                        Анализ сезонности:
                        • Тип сезонности: {seasonal_data.get('seasonality_type', 'Не выявлена')}
                        • Текущий сезонный коэффициент: {seasonal_factor:.2f}
                        
                        Рекомендация: {'увеличить размер заказа на ' + str((seasonal_factor - 1) * 100) + '%' if seasonal_factor > 1.1 else 'использовать стандартный размер заказа'}
                        """
                    }
            except Exception as e:
                logger.error(f"Error in seasonality analysis: {str(e)}")
                seasonality_info = {
                    "type": "NO_SEASONALITY",
                    "current_factor": 1.0,
                    "recommendation": "Не удалось проанализировать сезонность"
                }

            return {
                "frequent_orders": monthly_order,
                "quarterly_orders": quarterly_order,
                "seasonality": seasonality_info
            }

        except Exception as e:
            logger.error(f"Error in calculate_periodic_orders: {str(e)}")
            return {
                "frequent_orders": {
                    "order_size": 0,
                    "safety_stock": 0,
                    "total_size": 0,
                    "frequency": "Ежемесячно",
                    "details": "Ошибка расчета"
                },
                "quarterly_orders": {
                    "order_size": 0,
                    "safety_stock": 0,
                    "total_size": 0,
                    "frequency": "Ежеквартально",
                    "details": "Ошибка расчета"
                },
                "seasonality": {
                    "type": "NO_SEASONALITY",
                    "current_factor": 1.0,
                    "recommendation": "Ошибка анализа сезонности"
                }
            }     
        
    def get_full_recommendations(self) -> Dict:
        """Получение полных рекомендаций с деталями расчетов"""
        try:
            # Получаем все базовые расчеты
            consumption_data = self.total_consumption  # уже рассчитано в __init__
            lead_time_stats = self.calculate_lead_time_stats()
            reorder_point = self.calculate_reorder_point()
            optimal_qty = self.calculate_optimal_order_quantity()
            periodic_orders = self.calculate_periodic_orders()

            # Создаем раздел с базовыми показателями
            basic_calculations = {
                "title": "Базовые показатели для расчетов",
                "details": f"""
                ИСХОДНЫЕ РАСЧЕТЫ:

                1. Общее среднее потребление в день: {consumption_data['value']:.2f}
                {consumption_data['details']}

                2. Среднее время поставки: {lead_time_stats['avg']:.1f} дн
                {lead_time_stats['details']}
                """,
                # Trend detection fields
                "trend_detected": consumption_data.get('trend_detected', False),
                "yearly_avg": consumption_data.get('yearly_avg'),
                "recent_avg": consumption_data.get('recent_avg'),
                "growth_ratio": consumption_data.get('growth_ratio'),
            }

            return {
                "basic_calculations": basic_calculations,  # Добавляем новый раздел
                "reorder_point": reorder_point,
                "optimal_order_quantity": optimal_qty,
                "lead_time": lead_time_stats,
                "periodic_orders": periodic_orders,
                "safety_stock": {
                    "value": reorder_point["value"] - (
                        self.total_consumption["value"] * 
                        lead_time_stats["avg"]
                    ),
                    "details": f"""
                    Расчет страхового запаса:
                    1. Базовые значения:
                    • Точка заказа: {reorder_point["value"]:.2f}
                    • Общее среднее потребление в день: {consumption_data["value"]:.2f}
                    • Среднее время поставки: {lead_time_stats["avg"]:.1f} дней
                    
                    2. Формула расчета:
                    Страховой запас = Точка заказа - (Среднее потребление × Среднее время поставки)
                    
                    3. Расчет:
                    {reorder_point["value"]:.2f} - ({consumption_data["value"]:.2f} × {lead_time_stats["avg"]:.1f}) = {reorder_point["value"] - (consumption_data["value"] * lead_time_stats["avg"]):.2f}
                    """
                }
            }
        except Exception as e:
            logger.error(f"Error in get_full_recommendations: {str(e)}")
            return {}
def get_material_order_history(material_id: int, months: int = 12) -> List[OrderHistory]:
    """Получение истории заказов материала из базы данных"""
    # Определяем период - 1 год от текущей даты
    end_date = timezone.now()
    start_date = end_date - timedelta(days=months * 30)
    
    # Получаем все заказы для материала за период
    orders = PurchaseOrder.objects.filter(
        items__raw_material_id=material_id,
        date__gte=start_date,
        date__lte=end_date
    ).select_related(
        'counterparty'
    ).prefetch_related(
        'items',
        'supplies'
    ).distinct()

    order_history = []
    for order in orders:
        # Находим позицию материала в заказе
        item = order.items.filter(raw_material_id=material_id).first()
        if not item:
            continue
            
        # Рассчитываем lead time
        lead_time = 0
        if order.supplies.exists():
            first_supply = order.supplies.order_by('date').first()
            if first_supply and first_supply.date > order.date:
                lead_time = (first_supply.date - order.date).days

        order_history.append(OrderHistory(
            quantity=float(item.quantity),
            lead_time=lead_time, 
            date=order.date.isoformat(),
            price=float(item.price),
            supplier_name=order.counterparty.name
        ))

    return order_history
