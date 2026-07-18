"""
Supply views — thin wrappers over api.services.supply_service.
"""
from django.http import JsonResponse
from rest_framework.decorators import api_view

from api.exceptions import NotFoundError, DataProcessingError
from api.serializers import ListQuerySerializer
from api.services.supply_service import (
    get_supply_analytics,
    get_supply_materials,
    get_materials_list,
    get_material_details,
    get_suppliers_list,
    get_supplier_details,
)

import logging

logger = logging.getLogger(__name__)


# =============================================================================
# Analytics Views
# =============================================================================

def supply_analytics(request):
    try:
        data = get_supply_analytics()
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_analytics: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных по поставкам")


def supply_materials(request):
    try:
        data = get_supply_materials(
            start_date=request.GET.get('start_date'),
            end_date=request.GET.get('end_date'),
            search=request.GET.get('search', '').strip(),
            group=request.GET.get('group', '').strip(),
        )
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_materials: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения данных о материалах")


# =============================================================================
# Materials Views
# =============================================================================

@api_view(['GET'])
def supply_materials_list(request):
    params = ListQuerySerializer.from_query_params(
        request.query_params,
        default_sort_field='total_quantity',
        allowed_sort_fields={
            'name', 'code', 'group', 'total_quantity', 'average_price',
            'total_sum', 'supplies_count', 'suppliers_count',
        },
    )
    try:
        data = get_materials_list(
            page=params['page'],
            page_size=params['page_size'],
            search=params['search'].strip(),
            group=params['group'].strip(),
            start_date=params.get('start_date') and params['start_date'].isoformat(),
            end_date=params.get('end_date') and params['end_date'].isoformat(),
            sort_field=params['sort_field'],
            sort_order=params['sort_order'],
        )
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_materials_list: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения списка материалов")


@api_view(['GET'])
def supply_material_details(request, material_id):
    try:
        data = get_material_details(
            material_id=material_id,
            start_date=request.GET.get('startDate'),
            end_date=request.GET.get('endDate'),
        )
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_material_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о материале")


# =============================================================================
# Suppliers Views
# =============================================================================

@api_view(['GET'])
def supply_suppliers_list(request):
    params = ListQuerySerializer.from_query_params(
        request.query_params,
        default_sort_field='supplies_count',
        allowed_sort_fields={
            'name', 'supplies_count', 'total_sum',
            'positions_count', 'last_supply',
        },
    )
    try:
        data = get_suppliers_list(
            page=params['page'],
            page_size=params['page_size'],
            search=params['search'].strip(),
            start_date=params.get('start_date') and params['start_date'].isoformat(),
            end_date=params.get('end_date') and params['end_date'].isoformat(),
            sort_field=params['sort_field'],
            sort_order=params['sort_order'],
        )
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_suppliers_list: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения списка поставщиков")


@api_view(['GET'])
def supply_supplier_details(request, supplier_id):
    try:
        data = get_supplier_details(
            supplier_id=supplier_id,
            start_date=request.GET.get('startDate'),
            end_date=request.GET.get('endDate'),
            material_id=request.GET.get('materialId'),
        )
        return JsonResponse({'status': 'success', 'data': data})
    except NotFoundError:
        raise
    except Exception as e:
        logger.error(f"Error in supply_supplier_details: {str(e)}", exc_info=True)
        raise DataProcessingError("Ошибка получения детальной информации о поставщике")
