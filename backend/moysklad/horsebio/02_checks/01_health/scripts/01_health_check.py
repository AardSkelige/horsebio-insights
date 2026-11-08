#!/usr/bin/env python3
"""
Проверка здоровья себестоимости - универсальный скрипт.

Находит все типы ошибок:
1. FIFO-себестоимость 0.00 — цена не указана ни в одном документе
2. Огромные отклонения FIFO-себестоимости vs последняя приёмка (неправильные ед. изм.)
3. Значительные отклонения FIFO-себестоимости vs последняя приёмка (рост цен, накладные)
4. Малые отклонения (округление копеек)
5. Свежие оприходования с ценой, не совпадающей с приёмкой на тот момент
6. Отрицательные остатки по складам
7. Оприходования на внутренних складах — могут быть перемещениями; нет ячейки на Шатле (всегда)
8. Списания с нарушениями — без описания, нулевая цена или нет ячейки на Шатле (всегда)
9. Инвентаризации с расхождениями — без описания или большое расхождение (всегда)
10. Перемещения с нарушениями — нет ячейки, обратное направление, крупное без описания (всегда)
11. Приёмки с нарушениями — цена 0, нет ячейки на Шатле, нет описания, неожиданный склад (всегда)
12. Скачки цен в приёмках по группам товаров (--full)
13. Коды товаров: без кода, дубли, аномалии (Материалы, Товары, Этикетки)
14. Возвраты от покупателей с нулевой себестоимостью — занижают FIFO-себестоимость готовой продукции (всегда)
15. Оприходования с нулевой ценой позиций — занижают FIFO-себестоимость любого товара (всегда)
16. Зависшие производственные задания — план прошёл больше месяца назад, а ожидание или резерв висят (всегда)

Использование:
    python3 01_health_check.py                           # Проверка с порогом 5%
    python3 01_health_check.py --threshold 1.0           # Изменить порог себестоимости
    python3 01_health_check.py --store-id XXX            # Конкретный склад
    python3 01_health_check.py --enter-months 1          # Оприходования за 1 мес. (по умол. 3)
    python3 01_health_check.py --doc-months 1            # Списания/инв./перемещения за 1 мес.
    python3 01_health_check.py --inv-threshold 10        # Порог расхождения в инв., ед.
    python3 01_health_check.py --move-threshold 5000     # Порог суммы перемещения, руб
    python3 01_health_check.py --full                    # + скачки цен (порог 30%)
    python3 01_health_check.py --full --supply-threshold 20  # Изменить порог скачка
    python3 01_health_check.py --full --prev-count 5     # Больше предыдущих приёмок
    python3 01_health_check.py --full --max-months 6     # Только приёмки за 6 месяцев
    cd 02_checks/01_health/scripts && python3 01_health_check.py --full
"""

import sys
import os
import json
import argparse
from datetime import datetime, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN

from health_config import DEFAULT_STORES
from health_fifo import FifoChecksMixin
from health_docs_stock import StockDocChecksMixin
from health_docs_inventory import InventoryChecksMixin
from health_docs_flow import FlowDocChecksMixin
from health_supply_jumps import SupplyJumpChecksMixin
from health_sheet_prices import SheetPriceChecksMixin
from health_codes import CodeChecksMixin
from health_report_console import ConsoleReportMixin
from health_report_export import ExportReportMixin
from health_production import ProductionChecksMixin


class CostHealthCheck(
    FifoChecksMixin, StockDocChecksMixin, InventoryChecksMixin, FlowDocChecksMixin, SupplyJumpChecksMixin, SheetPriceChecksMixin, CodeChecksMixin,
    ProductionChecksMixin, ConsoleReportMixin, ExportReportMixin,
):
    """Проверка здоровья себестоимости"""

    def __init__(self, helper, threshold=5.0, supply_threshold=30.0, prev_count=3,
                 max_months=12, enter_months=3, doc_months=3,
                 inv_threshold=50, move_threshold=10000, full_mode=False,
                 supply_min_rub=3000.0):
        self.h = helper
        self.full_mode = full_mode
        self.threshold = threshold
        self.supply_threshold = supply_threshold
        self.supply_min_rub = supply_min_rub
        self.prev_count = prev_count
        self.max_months = max_months
        self.enter_months = enter_months
        self.doc_months = doc_months
        self.inv_threshold = inv_threshold
        self.move_threshold = move_threshold
        self.cutoff_date = datetime.now() - timedelta(days=max_months * 30)

        # Счётчик секций для единого вывода "Проверка N/M"
        self._check_num = 0
        self._total_checks = 0  # Устанавливается перед запуском

        # Загрузка подтверждённых документов
        self.ack_ids           = self._load_ack('enters_acknowledged.json')
        self.loss_ack_ids      = self._load_ack('losses_acknowledged.json')
        self.inventory_ack_ids = self._load_ack('inventories_acknowledged.json')
        self.move_ack_ids      = self._load_ack('moves_acknowledged.json')
        self.supply_ack_ids    = self._load_ack('supplies_acknowledged.json')
        self.enter_zero_ack_ids  = self._load_ack('enter_zero_acknowledged.json')
        self.deviations_notes_map = self._load_deviations_notes()

        # Статистика
        self.stats = {
            'total': 0,
            'critical': [],        # Цена 0.00 или отклонение >50%
            'important': [],       # Отклонение 5-50%
            'warnings': [],        # Отклонение 1-5%
            'ok': 0,               # Отклонение <1%
            'scanned': {},         # {store_name: кол-во товаров} — для пояснения в статистике
            'negative_stock': [],  # Отрицательные остатки [{name, store, qty}]
            'suspect_enters': [],  # Оприходования на внутренних складах
            'suspect_losses': [],        # Списания с подозрительными признаками
            'suspect_inventories': [],   # Инвентаризации с расхождениями
            'inventory_price_issues': [], # Инвентаризации с нулевыми или аномальными ценами
            'suspect_moves': [],         # Перемещения с нарушениями
            'suspect_supplies': [],      # Приёмки с нарушениями
            'supply_jumps': [],           # Скачки цен в приёмках (требуют внимания)
            'supply_jumps_explained': [], # Скачки с известной причиной (проверяются, но не критичны)
            'supply_jumps_ignored': 0,    # Устаревший счётчик (для обратной совместимости)
            'enter_zero_prices': [],      # Оприходования с нулевой ценой позиций
            'enter_price_issues': [],     # Свежие оприходования с ценой, не совпадающей с приёмкой на тот момент
            'code_no_code': [],           # Товары без кода
            'code_duplicates': {},        # {code: [products]} — дублирующиеся коды
            'code_suspect': [],           # Товары с кодом-аномалией (не соответствует паттерну группы)
            'stale_drafts': [],           # Непроведённые документы старше порога [{type, doc_name, age_days}]
            'stuck_production': [],
            'stuck_production_failed': [],
        }

    def _elapsed_str(self):
        import time as _t
        elapsed = _t.time() - self._start_time if hasattr(self, '_start_time') else 0
        mins, secs = divmod(int(elapsed), 60)
        return f"{mins}м {secs}с" if mins else f"{secs}с"

    def _section_header(self, title, subtitle=None):
        """Напечатать заголовок секции с единым счётчиком Проверка N/M."""
        self._check_num += 1
        n = self._check_num
        m = self._total_checks
        print(f"\n{'='*70}")
        print(f"Проверка {n}/{m}: {title}")
        if subtitle:
            print(subtitle)
        print('='*70)

    def _load_ack(self, filename):
        """Загрузить список подтверждённых документов из JSON-файла рядом со скриптом."""
        path = os.path.join(os.path.dirname(__file__), '..', 'data', filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {item['doc_id'] for item in data.get('acknowledged', [])}
        except (FileNotFoundError, json.JSONDecodeError):
            return set()


def main():
    parser = argparse.ArgumentParser(description='Проверка здоровья себестоимости')
    parser.add_argument('--threshold', type=float, default=5.0,
                       help='Порог отклонения оприходований в %% (по умолчанию 5.0)')
    parser.add_argument('--store-id', type=str,
                       help='ID конкретного склада для проверки')
    parser.add_argument('--enter-months', type=int, default=3,
                       help='Глубина проверки оприходований на внутренних складах, мес. (по умолчанию 3)')
    parser.add_argument('--doc-months', type=int, default=3,
                       help='Глубина проверки списаний/инвентаризаций/перемещений, мес. (по умолчанию 3)')
    parser.add_argument('--inv-threshold', type=int, default=50,
                       help='Порог расхождения в инвентаризации, единиц суммарно (по умолчанию 50)')
    parser.add_argument('--move-threshold', type=int, default=10000,
                       help='Порог суммы перемещения без описания, руб (по умолчанию 10000)')
    parser.add_argument('--full', action='store_true',
                       help='Полная проверка: приёмки по группам + отрицательные остатки')
    parser.add_argument('--supply-threshold', type=float, default=30.0,
                       help='Порог изменения цены у того же поставщика, %% (по умолчанию 30.0)')
    parser.add_argument('--supply-min-rub', type=float, default=3000.0,
                       help='Изменение цены у того же поставщика меньше этой суммы на приёмку не показывается, руб (по умолчанию 3000)')
    parser.add_argument('--prev-count', type=int, default=3,
                       help='Сколько предыдущих приёмок брать для среднего (по умолчанию 3)')
    parser.add_argument('--max-months', type=int, default=12,
                       help='Не показывать скачки если последняя приёмка старше N месяцев (по умолчанию 12)')
    parser.add_argument('--results-out', type=str, default=None,
                       help='Путь для сохранения структурированного JSON находок (для страницы /checks)')
    args = parser.parse_args()

    h = ProductionHelper(MOYSKLAD_TOKEN)
    checker = CostHealthCheck(
        h,
        threshold=args.threshold,
        supply_threshold=args.supply_threshold,
        supply_min_rub=args.supply_min_rub,
        prev_count=args.prev_count,
        max_months=args.max_months,
        enter_months=args.enter_months,
        doc_months=args.doc_months,
        full_mode=args.full,
        inv_threshold=args.inv_threshold,
        move_threshold=args.move_threshold,
    )

    import time as _time
    import threading as _threading
    _start_time = _time.time()

    # Фоновый поток: тикающий таймер — обновляет строку каждую секунду
    _timer_stop = _threading.Event()
    def _timer_thread():
        _timer_stop.wait(1)  # ждём пока заголовок допечатается
        while not _timer_stop.is_set():
            elapsed = int(_time.time() - _start_time)
            m, s = divmod(elapsed, 60)
            t = f"{m}м {s:02d}с" if m else f"{s}с"
            sys.stdout.write(f"\r  ⏱  {t}   ")
            sys.stdout.flush()
            _timer_stop.wait(1)
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
    _threading.Thread(target=_timer_thread, daemon=True).start()

    print("="*70)
    print("ПРОВЕРКА ЗДОРОВЬЯ СЕБЕСТОИМОСТИ")
    print("="*70)
    print(f"Режим: {'ПОЛНЫЙ' if args.full else 'ОБЫЧНЫЙ'}")
    print(f"Порог отклонения оприходований: {args.threshold}%")
    if args.full:
        print(f"Порог скачка цен в приёмках: {args.supply_threshold}%")
        print(f"Предыдущих приёмок для среднего: {args.prev_count}")
        print(f"Игнорировать приёмки старше: {args.max_months} мес.")
    print()

    # Выбираем склады для проверки оприходований
    if args.store_id:
        store = h._get(f"/entity/store/{args.store_id}")
        stores = {args.store_id: store.get('name', 'N/A')}
    else:
        stores = DEFAULT_STORES

    checker._start_time = _start_time

    # Устанавливаем общее количество проверок для счётчика "Проверка N/M"
    # Фиксированные: по одной на каждый склад + 11 обязательных
    checker._total_checks = len(stores) + 11 + (1 if args.full else 0)

    # 1. Проверяем оприходования на каждом складе
    for store_id, store_name in stores.items():
        try:
            checker.check_store(store_id, store_name)
        except Exception as e:
            print(f"❌ Ошибка при проверке склада {store_name}: {e}\n")

    # 2. Проверяем отрицательные остатки (всегда)
    try:
        checker.check_negative_stock()
    except Exception as e:
        print(f"❌ Ошибка при проверке отрицательных остатков: {e}\n")

    # 3. Проверяем оприходования на внутренних складах (всегда)
    try:
        checker.check_suspect_enters()
    except Exception as e:
        print(f"❌ Ошибка при проверке оприходований: {e}\n")

    # 4. Проверяем списания (всегда)
    try:
        checker.check_suspect_losses()
    except Exception as e:
        print(f"❌ Ошибка при проверке списаний: {e}\n")

    # 5. Проверяем инвентаризации (всегда)
    try:
        checker.check_suspect_inventories()
    except Exception as e:
        print(f"❌ Ошибка при проверке инвентаризаций: {e}\n")

    # 6. Проверяем цены в инвентаризациях (всегда)
    try:
        checker.check_inventory_prices()
    except Exception as e:
        print(f"❌ Ошибка при проверке цен в инвентаризациях: {e}\n")

    # 7. Проверяем перемещения (всегда)
    try:
        checker.check_suspect_moves()
    except Exception as e:
        print(f"❌ Ошибка при проверке перемещений: {e}\n")

    # 8. Проверяем приёмки (всегда)
    try:
        checker.check_suspect_supplies()
    except Exception as e:
        print(f"❌ Ошибка при проверке приёмок: {e}\n")

    # 9. Коды товаров (всегда)
    try:
        checker.check_product_codes()
    except Exception as e:
        print(f"❌ Ошибка при проверке кодов товаров: {e}\n")

    # 14. Оприходования с нулевой ценой позиций (всегда)
    try:
        checker.check_enter_zero_prices()
    except Exception as e:
        print(f"❌ Ошибка при проверке нулевых цен в оприходованиях: {e}\n")

    # 15. Незавершённые черновики (всегда)
    try:
        checker.check_stale_drafts()
    except Exception as e:
        print(f"❌ Ошибка при проверке черновиков: {e}\n")

    try:
        checker.check_stuck_production()
    except Exception as e:
        print(f"❌ Ошибка при проверке производственных заданий: {e}\n")

    # 11. Полный режим: скачки цен в приёмках
    if args.full:
        try:
            checker.check_all_supply_prices()
        except Exception as e:
            print(f"❌ Ошибка при проверке скачков цен: {e}\n")

    # Итоговый отчёт
    _timer_stop.set()
    _elapsed = _time.time() - _start_time
    _mins, _secs = divmod(int(_elapsed), 60)
    checker.print_report()
    print(f"\n  Время выполнения: {_mins}м {_secs}с")

    # Структурированный JSON находок для страницы /checks
    if args.results_out:
        try:
            checker.export_results(args.results_out)
        except Exception as e:
            print(f"❌ Ошибка сохранения результатов JSON: {e}")


if __name__ == "__main__":
    main()
