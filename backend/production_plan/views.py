from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from api.services import fbo_stock
from api.services.ozon_stock import QUICK_PAUSES, OzonStockError
from api.utils.excel_export import ExcelReportBuilder
from production_plan.models import Exclusion, GreenItem
from production_plan.services import ozon_sales, wb_sales
from production_plan.services.articles import normalize
from production_plan.services.plan import full_months, plan

STATUS_LABELS = {'urgent': 'Срочно', 'produce': 'К производству', 'in_production': 'В производстве', 'enough': 'Хватает'}
MONTH_NAMES = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']


def _bad(message):
    return Response({'error': message}, status=400)


@api_view(['GET'])
def plan_view(request):
    return Response(plan(timezone.localdate()))


@api_view(['POST'])
def refresh(request):
    fbo_stock.get_data(force_refresh=True)
    try:
        ozon_sales.sync(full_months(timezone.localdate()), QUICK_PAUSES)
    except OzonStockError as error:
        return Response({'error': f'Остатки обновлены, а продажи Ozon нет: {error}'}, status=502)
    if wb_sales.configured():
        try:
            wb_sales.sync(timezone.localdate(), wb_sales.QUICK_PAUSES)
        except wb_sales.WbSalesError as error:
            return Response({'error': f'Остатки и Ozon обновлены, а продажи WB нет: {error}'}, status=502)
    return Response(plan(timezone.localdate()))


@api_view(['GET'])
def export(request):
    data = plan(timezone.localdate())
    months = [MONTH_NAMES[month.month - 1] for month in data['months']]
    builder = ExcelReportBuilder('Производственный план')
    builder.add_headers(['Артикул', 'Название', *months, 'Обычно в месяц', 'Нужно на 2 мес', 'Можно взять', 'Хватит на, дней', 'В производстве', 'Произвести', 'Статус', 'Зелёный список'])
    for row in data['rows']:
        builder.add_row([
            row['article'], row['name'], *row['months'], row['usual'], row['need'], row['available'], row['days'],
            row['in_production'], row['produce'], STATUS_LABELS[row['status']], 'да' if row['green'] else '',
        ])
    builder.set_column_widths([16, 60, *[11] * len(months), 14, 14, 13, 14, 15, 12, 16, 15])
    return builder.to_http_response(f"production-plan-{timezone.localdate().isoformat()}.xlsx")


def _exclusions():
    return Response({'items': list(Exclusion.objects.values('id', 'text', 'note'))})


@api_view(['GET', 'POST'])
def exclusions(request):
    if request.method == 'POST':
        text = ' '.join(str(request.data.get('text') or '').split())
        if not text:
            return _bad('Впишите артикул или слово из названия')
        if len(text) > Exclusion._meta.get_field('text').max_length:
            return _bad('Слишком длинно: впишите артикул или одно слово')
        Exclusion.objects.get_or_create(text=text)
    return _exclusions()


@api_view(['DELETE'])
def exclusion_delete(request, pk):
    Exclusion.objects.filter(pk=pk).delete()
    return _exclusions()


@api_view(['POST', 'DELETE'])
def green(request):
    article = normalize(request.data.get('article'))
    if not article or len(article) > GreenItem._meta.get_field('article').max_length:
        return _bad('Нет артикула')
    if request.method == 'POST':
        GreenItem.objects.update_or_create(article=article, defaults={'name': str(request.data.get('name') or '')[:255]})
    else:
        GreenItem.objects.filter(article=article).delete()
    return Response({'article': article, 'green': request.method == 'POST'})
