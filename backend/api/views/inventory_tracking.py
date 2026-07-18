import logging
from datetime import datetime

from rest_framework.decorators import api_view
from rest_framework.response import Response

logger = logging.getLogger(__name__)


def _parse_month_param(month_str):
    """Parse '2026-04' → date(2026, 4, 1), or None if invalid/absent."""
    if not month_str:
        return None
    try:
        return datetime.strptime(month_str, "%Y-%m").date()
    except ValueError:
        return None


@api_view(['GET'])
def inventory_current(request):
    """
    Latest InventoryRun for the requested month.
    ?month=YYYY-MM  — specific month (default: current month)
    ?folder=Тара    — optional category filter
    """
    from inventory_tracking.models import InventoryRun

    month_param = request.GET.get('month', '').strip()
    month_start = _parse_month_param(month_param)

    if month_start:
        qs = InventoryRun.objects.filter(month_start=month_start)
    else:
        from datetime import date
        current_month = date.today().replace(day=1)
        qs = InventoryRun.objects.filter(month_start=current_month)

    latest_run = qs.order_by('-run_at').first()

    if not latest_run:
        label = month_param or datetime.now().strftime('%Y-%m')
        return Response({
            'status': 'no_data',
            'message': f'Данные за {label} ещё не загружены. Нажмите «Обновить сейчас».',
        })

    folder_filter = request.GET.get('folder', '').strip()
    products_qs = latest_run.products.all().order_by('folder', 'name')
    if folder_filter and folder_filter != 'Все':
        products_qs = products_qs.filter(folder=folder_filter)

    products = list(products_qs.values(
        'external_id', 'code', 'article', 'name', 'folder',
        'is_inventoried', 'inventory_count',
        'last_inventoried_at', 'days_since_last',
    ))

    return Response({
        'status': 'success',
        'data': {
            'run_at': latest_run.run_at,
            'month_start': latest_run.month_start,
            'total': latest_run.total_products,
            'inventoried': latest_run.inventoried_count,
            'not_inventoried': latest_run.not_inventoried_count,
            'triggered_by': latest_run.triggered_by,
            'is_snapshot': latest_run.is_month_snapshot,
            'products': products,
        },
    })


@api_view(['POST'])
def inventory_refresh(request):
    """
    Trigger a live MoySklad check.
    Body (JSON, optional): {"month": "2026-04"}
    """
    try:
        from inventory_tracking.services.inventory_checker import InventoryChecker, parse_month

        month_str = (request.data or {}).get('month', '')
        month_start = parse_month(month_str) if month_str else None

        run = InventoryChecker().run(triggered_by='manual', month_start=month_start)
        return Response({
            'status': 'success',
            'message': f'Проверка завершена. Найдено {run.total_products} позиций.',
            'run_at': run.run_at,
            'month_start': run.month_start,
            'total': run.total_products,
            'inventoried': run.inventoried_count,
            'not_inventoried': run.not_inventoried_count,
        })
    except Exception as e:
        logger.exception("Inventory refresh failed")
        return Response({'status': 'error', 'message': str(e)}, status=500)


@api_view(['POST'])
def inventory_upload_cells(request):
    """
    Upload МойСклад 'Инвентаризация с ячейками' XLS file.
    Merges article-level data into the existing InventoryRun for that month.

    multipart/form-data:
      file  — .xls file (шаблон inventory-address-warehouse-by-slot)
      month — optional YYYY-MM override (default: derived from file date)
    """
    file = request.FILES.get('file')
    if not file:
        return Response({'status': 'error', 'message': 'Файл не прикреплён'}, status=400)
    if not file.name.lower().endswith('.xls'):
        return Response({'status': 'error', 'message': 'Ожидается файл .xls из МойСклад'}, status=400)

    try:
        from inventory_tracking.services.xls_cells_parser import (
            parse_cells_inventory_xls,
            apply_cells_upload,
        )
        from inventory_tracking.models import InventoryRun

        parsed = parse_cells_inventory_xls(file)

        if not parsed['inventory_date']:
            return Response(
                {'status': 'error', 'message': 'Не удалось прочитать дату из файла'},
                status=400,
            )
        if not parsed['codes']:
            return Response(
                {'status': 'error', 'message': 'В файле не найдено позиций'},
                status=400,
            )

        month_param = (request.data or {}).get('month', '').strip()
        month_start = _parse_month_param(month_param) if month_param else None
        if month_start is None:
            month_start = parsed['inventory_date'].replace(day=1)

        run = InventoryRun.objects.filter(month_start=month_start).order_by('-run_at').first()
        if not run:
            label = month_start.strftime('%Y-%m')
            return Response(
                {
                    'status': 'error',
                    'message': (
                        f'Нет данных за {label}. '
                        'Сначала нажмите «Обновить» для загрузки из МойСклад.'
                    ),
                },
                status=404,
            )

        matched = apply_cells_upload(run, parsed['codes'], parsed['inventory_date'])

        # Save upload log (upsert by inventory_name only — one record per document)
        from inventory_tracking.models import CellsUploadLog
        CellsUploadLog.objects.update_or_create(
            inventory_name=parsed['inventory_name'] or file.name,
            defaults={
                'run': run,
                'month_start': month_start,
                'inventory_date': parsed['inventory_date'],
                'warehouse': parsed['warehouse'] or '',
                'codes': parsed['codes'],
                'matched_count': matched,
            },
        )

        inv_name = parsed['inventory_name'] or '?'
        inv_date = parsed['inventory_date'].strftime('%d.%m.%Y')
        return Response({
            'status': 'success',
            'message': (
                f'Инвентаризация {inv_name} от {inv_date}: '
                f'обновлено {matched} из {len(parsed["codes"])} позиций.'
            ),
            'inventory_name': parsed['inventory_name'],
            'inventory_date': parsed['inventory_date'],
            'warehouse': parsed['warehouse'],
            'matched_count': matched,
            'total_in_file': len(parsed['codes']),
            'run_inventoried': run.inventoried_count,
            'run_not_inventoried': run.not_inventoried_count,
            'run_total': run.total_products,
        })

    except ValueError as e:
        return Response({'status': 'error', 'message': str(e)}, status=400)
    except Exception:
        logger.exception("Cells inventory upload failed")
        return Response(
            {'status': 'error', 'message': 'Ошибка обработки файла. Проверьте формат.'},
            status=500,
        )


@api_view(['GET'])
def inventory_cells_log(request):
    """
    All uploaded 'с ячейками' records, optionally filtered by month.
    ?month=YYYY-MM — filter by month (default: all)
    Returns list ordered by inventory_date asc.
    """
    from inventory_tracking.models import CellsUploadLog

    month_param = request.GET.get('month', '').strip()
    month_start = _parse_month_param(month_param)

    qs = CellsUploadLog.objects.all()
    if month_start:
        qs = qs.filter(month_start=month_start)

    result = [
        {
            'id': entry.id,
            'inventory_name': entry.inventory_name,
            'inventory_date': entry.inventory_date,
            'warehouse': entry.warehouse,
            'matched_count': entry.matched_count,
            'uploaded_at': entry.uploaded_at,
            'month_start': entry.month_start,
        }
        for entry in qs.order_by('inventory_date')
    ]
    return Response({'status': 'success', 'data': result})


@api_view(['GET'])
def inventory_history(request):
    """
    All months that have at least one InventoryRun, with latest run stats per month.
    Used to populate the month picker and history table.
    """
    from inventory_tracking.models import InventoryRun
    from django.db.models import Max

    # Latest run_at per month_start
    month_runs = (
        InventoryRun.objects
        .values('month_start')
        .annotate(latest_run_at=Max('run_at'))
        .order_by('-month_start')
    )

    result = []
    for mr in month_runs:
        run = InventoryRun.objects.filter(
            month_start=mr['month_start'],
            run_at=mr['latest_run_at'],
        ).first()
        if run:
            result.append({
                'month_start': run.month_start,
                'run_at': run.run_at,
                'total': run.total_products,
                'inventoried': run.inventoried_count,
                'not_inventoried': run.not_inventoried_count,
                'is_snapshot': run.is_month_snapshot,
                'pct': round(run.inventoried_count / run.total_products * 100)
                       if run.total_products else 0,
            })

    return Response({'status': 'success', 'data': result})
