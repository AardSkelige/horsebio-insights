#!/usr/bin/env python3
"""
Подключение скриптов-роботов к базе через Django ORM.

Роботы — самостоятельные процессы, Django они не поднимают. Но состояние
им нужно хранить там же, где всё остальное: в файле на томе оно держится
только на том, что том не забыли смонтировать, а забытый том — это робот,
начавший с чистого листа.

Использование:

    from django_env import setup_django
    setup_django()
    from api.models import CdekWaybillState
"""
import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3]

_ready = False


def setup_django() -> None:
    """Поднять Django один раз за процесс."""
    global _ready
    if _ready:
        return

    if str(_BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(_BACKEND_DIR))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    import django
    django.setup()
    _ready = True


def refresh_connections() -> None:
    """Закрыть просроченные соединения с базой.

    Нужно демон-циклам: Django убирает их сам только на границе запроса,
    а её там нет. Без этого демон, простоявший ночь, падает на первом же
    обращении вместо переподключения.
    """
    setup_django()
    from django.db import close_old_connections

    close_old_connections()
