"""
ABC analysis views for product categorization by revenue contribution.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone

from forecasting.services.analysis.abc_analyzer import ABCAnalyzer
from api.exceptions import NotFoundError, DataProcessingError
from api.utils import get_period_dates, to_float_safe, ExcelReportBuilder

import logging
logger = logging.getLogger(__name__)


def _get_abc_period_dates(request):
    """
    Extract and calculate ABC analysis period dates from request.
    ABC analysis uses date() objects, not datetime.
    """
    end_date_str = request.GET.get('end_date')
    period_months = int(request.GET.get('period_months', 12))

    start_date, end_date = get_period_dates(end_date_str, period_months)

    # ABC analyzer expects date objects
    return start_date.date(), end_date.date(), period_months


@api_view(['GET'])
def abc_analysis(request):
    """API endpoint for ABC analysis."""
    try:
        start_date, end_date, period_months = _get_abc_period_dates(request)

        # Create analyzer and get results
        analyzer = ABCAnalyzer(start_date, end_date)
        analysis = analyzer.get_detailed_analysis()

        if 'error' in analysis:
            return Response({
                'status': 'error',
                'message': analysis['error']
            }, status=400)

        return Response({
            'status': 'success',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'months': period_months
            },
            'total_statistics': analysis['total_statistics'],
            'categories': {
                category: {
                    'metrics': {
                        'product_count': data['product_count'],
                        'revenue': data['revenue'],
                        'revenue_share': data['revenue_share'],
                        'quantity': data['quantity'],
                        'avg_monthly_revenue': data['avg_monthly_revenue'],
                        'avg_monthly_quantity': data['avg_monthly_quantity']
                    },
                    'products': [
                        {
                            'id': product['id'],
                            'name': product['name'],
                            'article': product['article'],
                            'group': product['group'],
                            'subgroup': product['subgroup'],
                            'metrics': {
                                'revenue': product['revenue'],
                                'revenue_share': product['revenue_share'],
                                'quantity': product['quantity'],
                                'avg_monthly_revenue': product['avg_monthly_revenue'],
                                'avg_monthly_quantity': product['avg_monthly_quantity'],
                                'orders_count': product['orders_count']
                            }
                        }
                        for product in data['products'][:10]  # Top 10 products per category
                    ]
                }
                for category, data in analysis['categories'].items()
            }
        })

    except Exception as e:
        logger.error(f"Error in abc_analysis: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка выполнения ABC-анализа")


@api_view(['GET'])
def abc_product_details(request, product_id):
    """API endpoint for detailed product info in ABC analysis."""
    try:
        start_date, end_date, period_months = _get_abc_period_dates(request)

        # Create analyzer
        analyzer = ABCAnalyzer(start_date, end_date)

        # Get detailed product info
        product_sales = analyzer.get_product_sales()
        product_data = product_sales.loc[
            product_sales['product__id'] == product_id
        ].to_dict('records')

        if not product_data:
            raise NotFoundError("Товар не найден")

        product_info = product_data[0]

        return Response({
            'status': 'success',
            'period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'months': period_months
            },
            'product': {
                'id': product_id,
                'name': product_info['product__name'],
                'article': product_info['product__article'],
                'group': product_info['product__group'],
                'subgroup': product_info['product__subgroup'],
            },
            'metrics': {
                'revenue': to_float_safe(product_info['total_revenue']),
                'revenue_share': to_float_safe(product_info['revenue_share']),
                'cumulative_share': to_float_safe(product_info['cumulative_share']),
                'quantity': to_float_safe(product_info['total_quantity']),
                'avg_monthly_revenue': to_float_safe(product_info['avg_monthly_revenue']),
                'avg_monthly_quantity': to_float_safe(product_info['avg_monthly_quantity']),
                'orders_count': int(product_info['orders_count']),
                'avg_price': to_float_safe(product_info['avg_price']),
                'category': product_info['category']
            }
        })

    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in abc_product_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о товаре")


@api_view(['GET'])
def export_abc_analysis(request):
    """API endpoint for exporting ABC analysis to Excel."""
    try:
        start_date, end_date, period_months = _get_abc_period_dates(request)

        # Create analyzer and get results
        analyzer = ABCAnalyzer(start_date, end_date)
        analysis = analyzer.get_detailed_analysis()

        if 'error' in analysis:
            return Response({
                'status': 'error',
                'message': analysis['error']
            }, status=400)

        # Prepare data for export
        all_products = []
        for category, category_data in analysis['categories'].items():
            for product in category_data['products']:
                all_products.append({
                    'name': product['name'],
                    'category': category,
                    'revenue': product['revenue'],
                    'revenue_share': product['revenue_share'],
                    'quantity': product['quantity'],
                    'orders_count': product['orders_count']
                })

        # Sort by revenue
        all_products.sort(key=lambda x: x['revenue'], reverse=True)

        # Build Excel using utility
        builder = ExcelReportBuilder("ABC-анализ")
        builder.add_headers([
            'Товар',
            'Категория ABC',
            'Выручка, ₽',
            'Доля в выручке, %',
            'Количество, шт.',
            'Количество заказов'
        ])

        # Add data rows
        for product in all_products:
            builder.add_row(
                [
                    product['name'],
                    f"Категория {product['category']}",
                    to_float_safe(product['revenue']),
                    to_float_safe(product['revenue_share']) * 100,
                    to_float_safe(product['quantity']),
                    int(product['orders_count'])
                ],
                number_formats={3: '#,##0.00', 4: '0.00%'}
            )

        builder.set_column_widths([50, 15, 15, 18, 15, 18])

        filename = f'abc_analysis_{end_date.strftime("%Y%m%d")}.xlsx'
        return builder.to_http_response(filename)

    except Exception as e:
        logger.error(f"Error in export_abc_analysis: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка экспорта ABC-анализа")
