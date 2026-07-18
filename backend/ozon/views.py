from datetime import datetime
import logging
import os
import tempfile

from django.http import HttpResponse
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .services.fbo_converter import FboConverter
from .services.ozon_client import OzonClient
from .services.report_generator import ReportGenerator


logger = logging.getLogger(__name__)


INTERNAL_ERROR_MESSAGE = 'Внутренняя ошибка сервера'


def _save_uploaded_file(uploaded_file, *, prefix):
    """Persist an upload under a unique private temporary path."""
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb', prefix=prefix, suffix='.xlsx', delete=False
    )
    try:
        for chunk in uploaded_file.chunks():
            temp_file.write(chunk)
    except Exception:
        temp_file.close()
        _delete_temp_file(temp_file.name)
        raise
    else:
        temp_file.close()
        return temp_file.name


def _delete_temp_file(path):
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Не удалось удалить временный файл %s", path)


@api_view(['GET'])
def export_advertising_data(request):
    """API endpoint для экспорта данных по рекламе в Excel"""
    try:
        # Получаем параметры дат из запроса
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        
        if not start_date or not end_date:
            return Response({
                'status': 'error',
                'message': 'Требуются параметры startDate и endDate'
            }, status=400)
        
        # Парсим даты
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        
        client = OzonClient()
        excel_data = client.export_advertising_data_by_date_range(start_date_obj, end_date_obj)
        
        if excel_data is None:
            return Response({
                'status': 'error',
                'message': 'Failed to create Excel file'
            }, status=400)
        
        current_date = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f'advertising_data_{start_date}_to_{end_date}_{current_date}.xlsx'
        
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in export_advertising_data: {e}")
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=500)


@api_view(['GET'])
def export_sales_data(request):
    """API endpoint для экспорта данных по продажам в Excel"""
    try:
        # Получаем параметры дат из запроса
        start_date = request.GET.get('startDate')
        end_date = request.GET.get('endDate')
        
        if not start_date or not end_date:
            return Response({
                'status': 'error',
                'message': 'Требуются параметры startDate и endDate'
            }, status=400)
        
        # Парсим даты
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        
        client = OzonClient()
        excel_data = client.export_sales_data_by_date_range(start_date_obj, end_date_obj)
        
        if excel_data is None:
            return Response({
                'status': 'error',
                'message': 'Failed to create Excel file'
            }, status=400)
        
        current_date = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f'sales_data_{start_date}_to_{end_date}_{current_date}.xlsx'
        
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception as e:
        logger.error(f"Error in export_sales_data: {e}")
        return Response({
            'status': 'error',
            'message': str(e)
        }, status=500)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def generate_report(request):
    try:
        logger.info("Files in request: %s", request.FILES)
        
        if 'ads_file' not in request.FILES or 'products_file' not in request.FILES:
            return Response({
                'status': 'error',
                'message': 'Both ads_file and products_file are required'
            }, status=400)
            
        ads_file = request.FILES['ads_file']
        products_file = request.FILES['products_file']
        
        logger.info(f"Got files: {ads_file.name}, {products_file.name}")
        logger.info(f"Ads file size: {ads_file.size} bytes")
        logger.info(f"Products file size: {products_file.size} bytes")
        logger.info(f"Ads file content type: {ads_file.content_type}")
        logger.info(f"Products file content type: {products_file.content_type}")
        
        # Проверяем что это правильные файлы по размеру и названию
        if 'sku' in ads_file.name.lower():
            logger.info("✅ ads_file выглядит как SKU файл")
        else:
            logger.error("❌ ads_file НЕ выглядит как SKU файл")
            
        if 'analytics' in products_file.name.lower() or 'report' in products_file.name.lower():
            logger.info("✅ products_file выглядит как Analytics файл")
        else:
            logger.error("❌ products_file НЕ выглядит как Analytics файл")
        
        generator = ReportGenerator()
        excel_data = generator.generate_report(ads_file, products_file)
        
        if excel_data is None:
            logger.info("Report generation failed - excel_data is None")
            return Response({
                'status': 'error',
                'message': 'Failed to generate report'
            }, status=400)
            
        current_date = datetime.now().strftime('%Y-%m-%d_%H-%M')
        filename = f'DRR_отчет_эффективность_рекламы_{current_date}.xlsx'
        
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception:
        logger.exception("Error in generate_report")
        return Response({
            'status': 'error',
            'message': INTERNAL_ERROR_MESSAGE
        }, status=500)
    

@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def process_competitors_info(request):
    """API endpoint для обработки данных о конкурентах"""
    temp_input_path = None
    try:
        if 'file' not in request.FILES:
            return Response({
                'status': 'error',
                'message': 'Не загружен файл'
            }, status=400)
            
        input_file = request.FILES['file']
        
        logger.info(f"Получен файл: {input_file.name}")
        
        temp_input_path = _save_uploaded_file(
            input_file, prefix='input_competitors_'
        )
        
        # Импортируем функцию из скрипта
        from .services.competitors_analyzer import process_ozon_data
        
        # Получаем данные обработанного файла
        excel_data = process_ozon_data(temp_input_path)
        
        if excel_data is None:
            return Response({
                'status': 'error',
                'message': 'Не удалось обработать файл'
            }, status=400)
        
        current_date = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f'competitors_info_{current_date}.xlsx'
        
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception:
        logger.exception("Error in process_competitors_info")
        return Response({
            'status': 'error',
            'message': INTERNAL_ERROR_MESSAGE
        }, status=500)
    finally:
        _delete_temp_file(temp_input_path)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def process_stock_availability(request):
    """API endpoint для обработки данных о доступности товаров"""
    temp_input_path = None
    try:
        if 'file' not in request.FILES:
            return Response({
                'status': 'error',
                'message': 'Не загружен файл'
            }, status=400)
            
        input_file = request.FILES['file']
        
        logger.info(f"Получен файл: {input_file.name}")
        
        temp_input_path = _save_uploaded_file(
            input_file, prefix='input_stock_'
        )
        
        # Импортируем функцию из скрипта
        from .services.stock_analyzer import process_availability_data
        
        # Получаем данные обработанного файла
        excel_data = process_availability_data(temp_input_path)
        
        if excel_data is None:
            return Response({
                'status': 'error',
                'message': 'Не удалось обработать файл'
            }, status=400)
            
        current_date = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f'stock_availability_{current_date}.xlsx'
        
        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        return response
        
    except Exception:
        logger.exception("Error in process_stock_availability")
        return Response({
            'status': 'error',
            'message': INTERNAL_ERROR_MESSAGE
        }, status=500)
    finally:
        _delete_temp_file(temp_input_path)


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def convert_fbo_supply(request):
    """Конвертирует файл с прогнозом в Excel для FBO-поставки Ozon"""
    try:
        if 'file' not in request.FILES:
            return Response({
                'status': 'error',
                'message': 'Не загружен файл'
            }, status=400)

        input_file = request.FILES['file']
        logger.info(f"FBO конвертер: получен файл {input_file.name}")

        converter = FboConverter()
        excel_data = converter.convert(input_file)

        current_date = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f'fbo_supply_{current_date}.xlsx'

        response = HttpResponse(
            excel_data,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    except Exception:
        logger.exception("Error in convert_fbo_supply")
        return Response({
            'status': 'error',
            'message': INTERNAL_ERROR_MESSAGE
        }, status=500)
