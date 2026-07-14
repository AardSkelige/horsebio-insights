# sync/views.py

from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import ensure_csrf_cookie
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Shipment, RawMaterial, Counterparty
from .sync_task import TaskManager, ParserTask
from .logger import logger, structured_logger

import json
import time
from datetime import datetime as dt

from contextlib import contextmanager
from django.db import connection

# Создаем единственный экземпляр TaskManager
task_manager = TaskManager()

@contextmanager
def close_old_connections():
    try:
        yield
    finally:
        connection.close()

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
                    'months_back': months
                }
        except ValueError:
            raise ValidationError("Некорректный формат даты")

        response = task_manager.start_task(ParserTask, **params)
        structured_logger.success(f"Задача запущена: {response.get('message', 'OK')}")

        if response['status'] != 'started':
            raise ValidationError(f"Failed to start task: {response.get('message', 'Unknown error')}")

        return Response(response)

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
    """Остановка загрузки данных"""
    try:
        structured_logger.info("Получен запрос на остановку загрузки")
        response = task_manager.stop_current_task()

        return Response({
            'status': 'success',
            'message': 'Задача остановлена или уже не выполняется'
        })

    except Exception as e:
        logger.exception("Error in stop_loading")
        return Response({
            'status': 'error',
            'message': f'Ошибка при остановке загрузки: {str(e)}'
        }, status=500)

def stream_loading_progress(request):
    """Стриминг прогресса загрузки"""
    def event_stream():
        last_state = None
        last_state_time = 0
        task_active = True
        consecutive_empty_states = 0
        min_interval = 0.1

        try:
            while task_active:
                with close_old_connections():
                    current_time = time.time()

                    current_state = task_manager.get_current_state()

                    if not current_state:
                        consecutive_empty_states += 1
                        if consecutive_empty_states >= 3:
                            if not task_manager.is_task_running():
                                final_state = {
                                    'status': 'completed',
                                    'message': 'Задача завершена',
                                    'timestamp': timezone.now().isoformat()
                                }
                                yield f"data: {json.dumps(final_state)}\n\n"
                                task_active = False
                                break
                    else:
                        consecutive_empty_states = 0

                        time_elapsed = current_time - last_state_time
                        state_changed = (
                            not last_state or
                            current_state.get('message') != last_state.get('message') or
                            current_state.get('details') != last_state.get('details') or
                            current_state.get('status') != last_state.get('status') or
                            current_state.get('processed') != last_state.get('processed')
                        )

                        if state_changed and time_elapsed >= min_interval:
                            current_state['timestamp'] = timezone.now().isoformat()
                            yield f"data: {json.dumps(current_state)}\n\n"
                            last_state = current_state.copy()
                            last_state_time = current_time

                            if current_state.get('status') in ['completed', 'error', 'stopped']:
                                task_manager.cleanup_state()
                                task_active = False
                                break

                time.sleep(min_interval)

        except Exception as e:
            logger.exception("Error in event stream")
            error_state = {
                'status': 'error',
                'message': str(e),
                'timestamp': timezone.now().isoformat()
            }
            yield f"data: {json.dumps(error_state)}\n\n"
        finally:
            connection.close()

    response = StreamingHttpResponse(
        event_stream(),
        content_type='text/event-stream'
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response

@api_view(['GET'])
def get_task_status(request):
    """Получение текущего статуса задачи"""
    try:
        is_running = task_manager.is_task_running()
        current_state = task_manager.get_current_state() if is_running else None

        return Response({
            'is_running': is_running,
            'state': current_state
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
