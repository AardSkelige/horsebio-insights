# sync/views.py

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Shipment, RawMaterial, Counterparty, SyncRun
from . import runner
from .logger import logger, structured_logger

from datetime import datetime as dt


@api_view(['GET'])
@ensure_csrf_cookie
def home(request):
    """Домашняя страница со статистикой"""
    stats = {
        'shipments_count': Shipment.objects.filter(
            items__product__group='Товары',
            items__product__subgroup__isnull=False
        ).exclude(
            items__product__subgroup=''
        ).distinct().count(),
        'materials_count': RawMaterial.objects.count(),
        'counterparties_count': Counterparty.objects.count(),
        'last_update': timezone.localtime(timezone.now()).strftime("%d.%m.%Y %H:%M")
    }
    return Response(stats)

@api_view(['POST'])
@ensure_csrf_cookie
def load_data(request):
    """Запуск загрузки данных"""
    try:
        structured_logger.info("Начало загрузки данных...")

        months = request.data.get('months', 12)
        start_date = request.data.get('startDate')
        end_date = request.data.get('endDate')

        try:
            if start_date and end_date:
                start_date = dt.strptime(start_date.split('T')[0], '%Y-%m-%d')
                end_date = dt.strptime(end_date.split('T')[0], '%Y-%m-%d').replace(
                    hour=23, minute=59, second=59
                )

                start_date = timezone.make_aware(start_date)
                end_date = timezone.make_aware(end_date)

                if start_date > end_date:
                    raise ValidationError("Дата начала не может быть позже даты окончания")

                if end_date.date() > timezone.now().date():
                    raise ValidationError("Дата окончания не может быть в будущем")

                params = {
                    'start_date': start_date,
                    'end_date': end_date
                }
            else:
                params = {
                    'months': months
                }
        except ValueError:
            raise ValidationError("Некорректный формат даты")

        try:
            run_id = runner.launch(**params)
        except runner.AlreadyRunning as busy:
            structured_logger.info(str(busy))
            return Response({'status': 'error', 'message': str(busy)}, status=409)

        structured_logger.success(f'Синхронизация запущена, прогон {run_id}')

        return Response({
            'status': 'started',
            'message': 'Задача успешно запущена',
            # Номер прогона нужен странице: без него она принимает за свой
            # прошлый, уже законченный прогон и гасит полосу.
            'run_id': run_id,
        })

    except ValidationError as e:
        structured_logger.error(f"Ошибка валидации: {str(e)}")
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=400)
    except Exception as e:
        logger.exception("Error in load_data")
        return Response({
            'status': 'error',
            'message': f'Ошибка при запуске загрузки: {str(e)}'
        }, status=500)

@api_view(['POST'])
def stop_loading(request):
    """Остановка загрузки данных.

    Просьба пишется в строку прогона, а не только в память процесса: нажавший
    «Стоп» вполне может сидеть в другом воркере, а прогон по расписанию идёт
    вообще отдельной командой. Сердцебиение задачи видит отметку и просит
    задачу остановиться — там же, где она и живёт.
    """
    try:
        structured_logger.info("Получен запрос на остановку загрузки")

        run = SyncRun.latest()
        if not run or not run.is_alive:
            return Response({
                'status': 'success',
                'message': 'Синхронизация уже не выполняется'
            })

        SyncRun.objects.filter(pk=run.pk).update(stop_requested=True)

        return Response({
            'status': 'success',
            'message': 'Остановка запрошена'
        })

    except Exception as e:
        logger.exception("Error in stop_loading")
        return Response({
            'status': 'error',
            'message': f'Ошибка при остановке загрузки: {str(e)}'
        }, status=500)

@api_view(['GET'])
def get_task_status(request):
    """Состояние синхронизации — из базы, а не из памяти процесса.

    В памяти его знает только тот процесс, где идёт задача. Под gunicorn
    воркеров несколько, и спрашивающий попадает не обязательно в нужный;
    а ночной прогон идёт вообще отдельной командой, и про него в памяти
    веб-процесса нет ничего.
    """
    try:
        run = SyncRun.latest()
        if not run:
            return Response({'is_running': False, 'state': None})

        return Response({
            'is_running': run.is_alive,
            'state': {
                'id': run.id,
                'status': run.status,
                'message': run.message,
                'processed': run.processed,
                'total': run.total,
                'started_at': run.started_at.isoformat(),
                'completed_at': run.finished_at.isoformat() if run.finished_at else None,
                'error': run.error or None,
                'triggered_by': run.triggered_by,
            },
        })
    except Exception as e:
        logger.exception("Error getting task status")
        return Response({
            'is_running': False,
            'state': None,
            'error': str(e)
        }, status=500)


@api_view(['GET'])
@ensure_csrf_cookie
def get_csrf_token(request):
    """Получение CSRF токена"""
    token = get_token(request)
    response = Response({'csrfToken': token})
    response['X-CSRFToken'] = token
    return response
