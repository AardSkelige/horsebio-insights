"""Страница «Остатки для FBO». Сбор данных — в api/services/fbo_stock.py."""

from datetime import datetime

from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.services.fbo_stock import get_data
from api.utils.excel_export import ExcelReportBuilder


@api_view(['GET'])
def fbo_stock(request):
    """Остатки для FBO. ?refresh=1 — мимо кеша, свежий запрос в МойСклад."""
    force = request.GET.get('refresh') in ('1', 'true')
    return Response({'status': 'success', 'data': get_data(force_refresh=force)})


@api_view(['GET'])
def fbo_stock_export(request):
    """Выгрузка в Excel: Артикул · Название · Количество · Ожидание."""
    data = get_data()
    rows = [item for item in data['items'] if not item['is_empty']]

    generated_at = datetime.fromisoformat(data['generated_at'])
    builder = ExcelReportBuilder("Остатки для FBO")
    builder.add_title_row(
        f"Остатки для FBO · {data['store']} · на {timezone.localtime(generated_at).strftime('%d.%m.%Y %H:%M')}",
        merge_cols=4,
    )
    builder.add_headers(['Артикул', 'Название', 'Количество', 'Ожидание'])
    for item in rows:
        builder.add_row([item['article'], item['name'], item['quantity'], item['in_transit']])
    builder.set_column_widths([18, 60, 14, 14])

    filename = f"fbo-stock-{timezone.localtime(generated_at).strftime('%Y-%m-%d')}.xlsx"
    return builder.to_http_response(filename)
