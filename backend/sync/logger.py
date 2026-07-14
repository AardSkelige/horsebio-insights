# sync/logger.py
# Merged from parser/logger_config.py + parser/logging_stream.py

import logging
import sys
import json
from queue import Queue
from datetime import datetime
from typing import Optional, Dict, Any


class StructuredFormatter(logging.Formatter):
    """Минималистичный форматтер"""

    LEVEL_COLORS = {
        'INFO': '',              # Без цвета для обычных сообщений
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'DEBUG': '\033[37m',     # White
        'CRITICAL': '\033[31m',  # Red
        'SUCCESS': '\033[32m',   # Green
        'SECTION': '\033[36m',   # Cyan
        'PROGRESS': '\033[35m',  # Magenta
        'STATS': '\033[34m',     # Blue
        'RESET': '\033[0m'       # Reset
    }

    def format(self, record):
        timestamp = datetime.now().strftime('%H:%M:%S')

        if hasattr(record, 'custom_color'):
            color = self.LEVEL_COLORS.get(record.custom_color, '')
        else:
            color = self.LEVEL_COLORS.get(record.levelname, '')

        reset = self.LEVEL_COLORS['RESET'] if color else ''

        message = f"{color}[{timestamp}] {record.getMessage()}{reset}"

        return message


class StructuredLogger:
    """Структурированный логгер"""

    def __init__(self, logger_instance):
        self.logger = logger_instance
        self.current_section = None
        self.indent_level = 0
        self.task_instance = None

    def section_start(self, title: str, description: Optional[str] = None):
        """Начало новой секции"""
        self.current_section = title

        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, title, (), None
        )
        record.custom_color = 'SECTION'
        self.logger.handle(record)

        if description:
            self.logger.info(f"  {description}")

    def section_end(self, title: str, summary: Optional[str] = None):
        """Завершение секции"""
        if summary:
            message = f"{title} завершен: {summary}"
        else:
            message = f"{title} завершен"

        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, message, (), None
        )
        record.custom_color = 'SUCCESS'
        self.logger.handle(record)

        self.current_section = None

    def subsection_start(self, title: str):
        """Начало подсекции"""
        self.logger.info(f"  {title}")

    def subsection_end(self, title: str, count: Optional[int] = None):
        """Завершение подсекции"""
        if count is not None:
            self.logger.info(f"  {title}: {count}")
        else:
            self.logger.info(f"  {title} завершен")

    def info(self, message: str, indent: Optional[int] = None, component: Optional[str] = None):
        """Информационное сообщение"""
        if indent and indent > 0:
            message = "  " * indent + message
        self.logger.info(message)

    def success(self, message: str, indent: Optional[int] = None, to_ui: bool = False):
        """Сообщение об успехе"""
        if indent and indent > 0:
            message = "  " * indent + message

        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, message, (), None
        )
        record.custom_color = 'SUCCESS'
        self.logger.handle(record)

        if to_ui and self.task_instance and hasattr(self.task_instance, 'update_progress'):
            self.task_instance.update_progress(details=message.strip())

    def warning(self, message: str, indent: Optional[int] = None):
        """Предупреждение"""
        if indent and indent > 0:
            message = "  " * indent + message

        record = self.logger.makeRecord(
            self.logger.name, logging.WARNING, "", 0, f"ВНИМАНИЕ: {message}", (), None
        )
        self.logger.handle(record)

    def error(self, message: str, indent: Optional[int] = None):
        """Сообщение об ошибке"""
        if indent and indent > 0:
            message = "  " * indent + message

        record = self.logger.makeRecord(
            self.logger.name, logging.ERROR, "", 0, f"ОШИБКА: {message}", (), None
        )
        self.logger.handle(record)

    def progress(self, message: str, current: int, total: int, indent: Optional[int] = None):
        """Сообщение о прогрессе"""
        percentage = (current / total * 100) if total > 0 else 0
        progress_msg = f"{message} ({current}/{total} - {percentage:.0f}%)"

        if indent and indent > 0:
            progress_msg = "  " * indent + progress_msg

        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, progress_msg, (), None
        )
        record.custom_color = 'PROGRESS'
        self.logger.handle(record)

    def period_info(self, start_date, end_date, found_count: int, task_instance=None):
        """Информация о периоде"""
        period_str = f"{start_date.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        message = f"  Период {period_str}: найдено {found_count}"
        self.info(message)

        if task_instance and hasattr(task_instance, 'update_progress'):
            status_message = "не требует обновления" if found_count == 0 else f"найдено {found_count}"
            task_instance.update_progress(
                details=f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}: {status_message}"
            )

    def stats(self, title: str, stats: Dict[str, Any]):
        """Вывод статистики"""
        stats_str = ", ".join([f"{k}: {v}" for k, v in stats.items()])
        message = f"{title}: {stats_str}"

        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, message, (), None
        )
        record.custom_color = 'STATS'
        self.logger.handle(record)


class LoggingStream:
    """Класс для хранения и управления потоком логов загрузки"""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.log_queue = Queue()
            cls._instance.current_status = {
                'status': 'idle',
                'progress': 0,
                'total': 0
            }
        return cls._instance

    def clear(self):
        """Очистка очереди логов"""
        while not self.log_queue.empty():
            self.log_queue.get()
        self.current_status = {
            'status': 'idle',
            'progress': 0,
            'total': 0
        }

    def add_log(self, message, level='info'):
        """Добавление сообщения в лог"""
        log_entry = {
            'level': level,
            'message': message
        }
        self.log_queue.put(json.dumps(log_entry))

    def update_status(self, status, progress=None, total=None):
        """Обновление статуса загрузки"""
        if progress is not None:
            self.current_status['progress'] = progress
        if total is not None:
            self.current_status['total'] = total
        self.current_status['status'] = status

    def get_status(self):
        """Получение текущего статуса"""
        return self.current_status

    def get_logs(self):
        """Получение всех новых логов"""
        logs = []
        while not self.log_queue.empty():
            logs.append(self.log_queue.get())
        return logs


def setup_logger(name=None):
    """Централизованная настройка логгера"""
    logger_name = name if name else 'sync'
    base_logger = logging.getLogger(logger_name)

    if base_logger.handlers:
        return base_logger

    base_logger.setLevel(logging.INFO)
    base_logger.handlers = []

    formatter = StructuredFormatter()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    base_logger.addHandler(console_handler)
    base_logger.propagate = False

    return base_logger


def get_structured_logger(name=None):
    """Получить структурированный логгер"""
    base_logger = setup_logger(name)
    return StructuredLogger(base_logger)


# Создаем единственный экземпляр логгера по умолчанию
logger = setup_logger()
structured_logger = StructuredLogger(logger)
