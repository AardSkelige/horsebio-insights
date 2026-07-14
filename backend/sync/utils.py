# sync/utils.py

from .logger import logger, structured_logger


def get_group_from_pathname(pathname):
    """Определяет группу на основе pathName"""
    if not pathname:
        return None

    # Преобразуем всё в нижний регистр сразу
    pathname_lower = pathname.lower()

    # Специальные случаи для конкретных путей
    if pathname_lower == 'не вошедшее старье':
        structured_logger.info(f"  Специальный случай: '{pathname}' → Материалы для производства")
        return 'Материалы для производства'

    # Если pathname содержит слеши, берем первую часть
    if '/' in pathname_lower:
        pathname_lower = pathname_lower.split('/')[0].lower()

    group_mapping = {
        'тара': 'Тара',
        'пробники': 'Пробники',
        'материалы для производства': 'Материалы для производства',
        'материалы': 'Материалы для производства',
        'товары': 'Товары',
        'этикетки': 'Этикетки'
    }

    # Проверяем точное совпадение
    for key, value in group_mapping.items():
        if pathname_lower == key:
            structured_logger.info(f"  Группа определена: '{pathname}' → {value}")
            return value

    # Проверяем частичное совпадение
    for key, value in group_mapping.items():
        if key in pathname_lower:
            structured_logger.info(f"  Группа определена: '{pathname}' → {value}")
            return value

    structured_logger.warning(f"Не удалось определить группу для: '{pathname}'")
    return None
