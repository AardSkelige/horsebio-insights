#!/usr/bin/env python3
"""
Cash flow views - HTTP layer only.
Business logic is in api.services.cash_flow
"""
import logging
import json
import requests
from datetime import datetime

from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods

from api.exceptions import ExternalServiceError, DataProcessingError
from api.services.cash_flow import (
    get_operations_data,
    get_expense_items,
    get_expense_categories_by_api,
    get_sales_channels,
    get_payments_by_channels,
    get_income_channels_from_payments,
    get_last_full_month_dates,
    generate_moysklad_link,
    calculate_initial_balance,
    export_to_excel,
)

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
def cash_flow_report(request):
    """
    API endpoint для получения отчета движения денежных средств
    """
    try:
        data = json.loads(request.body)
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        # Если даты не переданы, используем последний полный месяц
        if not date_from or not date_to:
            date_from, date_to = get_last_full_month_dates()

        # Получаем операции
        operations_data = get_operations_data(date_from, date_to)

        # Получаем каналы продаж
        channels_dict = get_sales_channels()

        # Получаем платежи по каналам из уже загруженных операций
        channel_payments = get_payments_by_channels(channels_dict, operations_data)

        # Получаем статьи расходов
        expense_items_dict = get_expense_items()

        # Анализируем расходы
        expense_categories, excluded_categories, expense_categories_with_ids, excluded_categories_with_ids = get_expense_categories_by_api(operations_data, expense_items_dict)

        # Рассчитываем итоги
        total_income = 0
        total_expense_raw = 0

        for operation_type, operations in operations_data.items():
            if not operations:
                continue

            for operation in operations:
                sum_value = operation.get('sum', 0)
                amount = sum_value / 100 if sum_value else 0

                if operation_type in ['cashout', 'paymentout', 'retaildrawercashout']:
                    total_expense_raw += amount
                elif operation_type in ['cashin', 'paymentin', 'retaildrawercashin']:
                    total_income += amount

        # Исключаем операции перемещения из общих расходов
        total_excluded = sum(excluded_categories.values()) if excluded_categories else 0
        total_expense = total_expense_raw - total_excluded

        # Получаем каналы дохода
        income_channels = get_income_channels_from_payments(channel_payments, operations_data)

        # Рассчитываем начальный остаток на дату начала периода
        initial_balance = calculate_initial_balance(date_from)

        # Чистый денежный поток
        net_cash_flow = total_income - total_expense
        final_balance = initial_balance + net_cash_flow

        # Прибыль = Общий приход - Общий расход
        profit = total_income - total_expense

        # Генерируем ссылки МойСклад для статей расходов
        expense_categories_with_links = {}
        for category, amount in expense_categories.items():
            expense_item_id = expense_categories_with_ids.get(category)
            moysklad_link = None
            if expense_item_id:
                moysklad_link = generate_moysklad_link(date_from, date_to, expense_item_id, category)

            expense_categories_with_links[category] = {
                'amount': amount,
                'moysklad_link': moysklad_link,
                'expense_item_id': expense_item_id
            }

        # Генерируем ссылки для исключенных категорий
        excluded_categories_with_links = {}
        for category, amount in excluded_categories.items():
            expense_item_id = excluded_categories_with_ids.get(category)
            moysklad_link = None
            if expense_item_id:
                moysklad_link = generate_moysklad_link(date_from, date_to, expense_item_id, category)

            excluded_categories_with_links[category] = {
                'amount': amount,
                'moysklad_link': moysklad_link,
                'expense_item_id': expense_item_id
            }

        response_data = {
            'success': True,
            'data': {
                'period': {
                    'from': date_from,
                    'to': date_to
                },
                'initial_balance': initial_balance,
                'income': {
                    'total': total_income,
                    'channels': income_channels
                },
                'expense': {
                    'total': total_expense,
                    'categories': expense_categories_with_links
                },
                'excluded': excluded_categories_with_links,
                'net_cash_flow': net_cash_flow,
                'profit': profit,
                'final_balance': final_balance
            }
        }

        return JsonResponse(response_data)

    except requests.RequestException as e:
        logger.error(f"External API error in cash_flow_report: {str(e)}", exc_info=True)
        raise ExternalServiceError("Ошибка подключения к МойСклад API")
    except Exception as e:
        logger.error(f"Error in cash_flow_report: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка формирования отчета о движении денежных средств")


@require_http_methods(["POST"])
def cash_flow_export(request):
    """
    API endpoint для экспорта отчета движения денежных средств в Excel
    """
    try:
        data = json.loads(request.body)
        date_from = data.get('date_from')
        date_to = data.get('date_to')

        # Если даты не переданы, используем последний полный месяц
        if not date_from or not date_to:
            date_from, date_to = get_last_full_month_dates()

        # Получаем все данные (аналогично cash_flow_report)
        operations_data = get_operations_data(date_from, date_to)
        channels_dict = get_sales_channels()
        channel_payments = get_payments_by_channels(channels_dict, operations_data)
        expense_items_dict = get_expense_items()
        expense_categories, excluded_categories, _, _ = get_expense_categories_by_api(operations_data, expense_items_dict)

        # Рассчитываем итоги
        total_income = 0
        total_expense_raw = 0

        for operation_type, operations in operations_data.items():
            for operation in operations:
                sum_value = operation.get('sum', 0)
                amount = sum_value / 100 if sum_value else 0

                if operation_type in ['cashout', 'paymentout', 'retaildrawercashout']:
                    total_expense_raw += amount
                elif operation_type in ['cashin', 'paymentin', 'retaildrawercashin']:
                    total_income += amount

        total_excluded = sum(excluded_categories.values()) if excluded_categories else 0
        total_expense = total_expense_raw - total_excluded

        income_channels = get_income_channels_from_payments(channel_payments, operations_data)

        # Рассчитываем начальный остаток на дату начала периода
        initial_balance = calculate_initial_balance(date_from)

        # Форматируем даты для отображения
        period_from = datetime.fromisoformat(date_from.replace('T', ' ').replace('.000', '')).strftime('%d.%m.%Y %H:%M')
        period_to = datetime.fromisoformat(date_to.replace('T', ' ').replace('.000', '')).strftime('%d.%m.%Y %H:%M')

        # Создаем Excel файл
        excel_buffer = export_to_excel(
            income_channels,
            expense_categories,
            total_income,
            total_expense,
            period_from,
            period_to,
            initial_balance,
            excluded_categories
        )

        # Возвращаем файл
        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cash_flow_report_{timestamp}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    except requests.RequestException as e:
        logger.error(f"External API error in cash_flow_export: {str(e)}", exc_info=True)
        raise ExternalServiceError("Ошибка подключения к МойСклад API")
    except Exception as e:
        logger.error(f"Error in cash_flow_export: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка экспорта отчета о движении денежных средств")
