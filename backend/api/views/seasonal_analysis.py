"""
Seasonal analysis views for product seasonality patterns.
"""
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.db.models import F, Sum, Count, DecimalField

from core.models import ShipmentItem, Product
from forecasting.services.analysis.abc_analyzer import ABCAnalyzer
from forecasting.services.analysis.seasonal_demand_analyzer import SeasonalDemandAnalyzer
from api.utils import get_period_dates, to_float_safe

import logging
logger = logging.getLogger(__name__)

# Mapping of seasonality types to Russian names
SEASONALITY_NAMES = {
    'STABLE': 'Стабильные продажи',
    'SUMMER': 'Летний сезон',
    'WINTER': 'Зимний сезон',
    'MULTI_PEAK': 'Несколько пиков',
    'UNCERTAIN': 'Неопределенная сезонность'
}


@api_view(['GET'])
def seasonal_analysis(request):
    """API endpoint for seasonal analysis of products."""
    try:
        # Get parameters from request
        category = request.GET.get('category', 'A')
        period_months = int(request.GET.get('period_months', 12))
        end_date_str = request.GET.get('end_date')

        # Calculate date range using utility
        start_date, end_date = get_period_dates(end_date_str, period_months)

        # Get products for selected category through ABC analysis
        abc_analyzer = ABCAnalyzer(start_date, end_date)
        abc_analysis = abc_analyzer.get_detailed_analysis()

        if 'error' in abc_analysis:
            return Response({
                'status': 'error',
                'message': abc_analysis['error']
            }, status=400)

        category_products = abc_analysis['categories'][category]['products']

        # Analyze seasonality for each product
        seasonal_analyzer = SeasonalDemandAnalyzer(start_date, end_date)
        products_with_seasonality = []

        for product in category_products:
            sales_history = seasonal_analyzer.get_sales_history(product['id'])
            if not sales_history.empty:
                seasonality = seasonal_analyzer.analyze_seasonality_pattern(sales_history)
                products_with_seasonality.append({
                    'id': product['id'],
                    'name': product['name'],
                    'article': product.get('article', ''),
                    'seasonality_type': seasonality['seasonality_type'],
                    'seasonality_name': SEASONALITY_NAMES.get(
                        seasonality['seasonality_type'], 'Неизвестно'
                    ),
                    'seasonal_factors': {
                        int(k): to_float_safe(v)
                        for k, v in seasonality['seasonal_factors'].items()
                    },
                    'stability_metrics': {
                        'coefficient_std': to_float_safe(
                            seasonality['stability_metrics']['coefficient_std']
                        ),
                        'max_deviation': to_float_safe(
                            seasonality['stability_metrics']['max_deviation']
                        ),
                        'peaks_count': int(
                            seasonality['stability_metrics'].get('peaks_count', 0)
                        ),
                        'troughs_count': int(
                            seasonality['stability_metrics'].get('troughs_count', 0)
                        )
                    }
                })

        return Response({
            'status': 'success',
            'data': {
                'products': products_with_seasonality,
                'total_products': len(products_with_seasonality),
                'period': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'months': period_months
                }
            }
        })

    except Exception as e:
        logger.error(f"Error in seasonal_analysis: {str(e)}")
        return Response({
            'status': 'error',
            'message': f'Ошибка при анализе данных: {str(e)}'
        }, status=500)


@api_view(['GET'])
def seasonal_product_details(request, product_id):
    """API endpoint for detailed seasonal analysis of a specific product."""
    try:
        period_months = int(request.GET.get('period_months', 12))
        end_date_str = request.GET.get('end_date')

        # Calculate date range using utility
        start_date, end_date = get_period_dates(end_date_str, period_months)

        # Get product info
        product = Product.objects.get(id=product_id)

        # Analyze seasonality
        analyzer = SeasonalDemandAnalyzer(start_date, end_date)
        sales_history = analyzer.get_sales_history(product_id)

        if sales_history.empty:
            return Response({
                'status': 'error',
                'message': 'Нет данных о продажах'
            }, status=404)

        seasonality = analyzer.analyze_seasonality_pattern(sales_history)

        # Convert Series to dict with numeric values
        monthly_sales = {
            k.strftime('%Y-%m'): to_float_safe(v)
            for k, v in sales_history.items()
        }

        # Ensure all seasonal factors are numbers
        seasonal_factors = {
            int(k): to_float_safe(v)
            for k, v in seasonality['seasonal_factors'].items()
        }

        # Convert stability metrics
        stability_metrics = {
            'coefficient_std': to_float_safe(
                seasonality['stability_metrics']['coefficient_std']
            ),
            'max_deviation': to_float_safe(
                seasonality['stability_metrics']['max_deviation']
            ),
            'peaks_count': int(seasonality['stability_metrics'].get('peaks_count', 0)),
            'troughs_count': int(seasonality['stability_metrics'].get('troughs_count', 0))
        }

        # Convert peaks and troughs
        peaks = [
            {
                'month': str(peak['month']),
                'deviation_percent': to_float_safe(peak['deviation_percent'])
            }
            for peak in seasonality.get('peaks', [])
        ]

        troughs = [
            {
                'month': str(trough['month']),
                'deviation_percent': to_float_safe(trough['deviation_percent'])
            }
            for trough in seasonality.get('troughs', [])
        ]

        # Get sales statistics
        sales_stats = ShipmentItem.objects.filter(
            product_id=product_id,
            shipment__date__range=(start_date, end_date)
        ).aggregate(
            total_revenue=Sum(F('price') * F('quantity'), output_field=DecimalField()),
            total_quantity=Sum('quantity'),
            orders_count=Count('shipment', distinct=True)
        )

        response_data = {
            'status': 'success',
            'data': {
                'id': product.id,
                'name': product.name,
                'article': product.article,
                'group': product.group,
                'monthly_sales': monthly_sales,
                'seasonal_factors': seasonal_factors,
                'seasonality_type': seasonality['seasonality_type'],
                'peaks': peaks,
                'troughs': troughs,
                'stability_metrics': stability_metrics,
                'sales_stats': {
                    'total_revenue': to_float_safe(sales_stats['total_revenue']),
                    'total_quantity': int(sales_stats['total_quantity'] or 0),
                    'avg_monthly_quantity': int(
                        (sales_stats['total_quantity'] or 0) / period_months
                    ),
                    'orders_count': int(sales_stats['orders_count'] or 0)
                }
            }
        }

        return Response(response_data)

    except Product.DoesNotExist:
        return Response({
            'status': 'error',
            'message': 'Продукт не найден'
        }, status=404)

    except Exception as e:
        logger.error(f"Error in seasonal_product_details: {str(e)}")
        return Response({
            'status': 'error',
            'message': f'Ошибка при анализе данных: {str(e)}'
        }, status=500)
