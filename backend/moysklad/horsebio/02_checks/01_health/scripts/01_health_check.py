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

Использование:
    python3 01_health_check.py                           # Проверка с порогом 5%
    python3 01_health_check.py --threshold 1.0           # Изменить порог себестоимости
    python3 01_health_check.py --store-id XXX            # Конкретный склад
    python3 01_health_check.py --enter-months 1          # Оприходования за 1 мес. (по умол. 3)
    python3 01_health_check.py --doc-months 1            # Списания/инв./перемещения за 1 мес.
    python3 01_health_check.py --inv-threshold 10        # Порог расхождения в инв., ед.
    python3 01_health_check.py --move-threshold 5000     # Порог суммы перемещения, руб
    python3 01_health_check.py --full                    # + скачки цен (порог 15%)
    python3 01_health_check.py --full --supply-threshold 20  # Изменить порог скачка
    python3 01_health_check.py --full --prev-count 5     # Больше предыдущих приёмок
    python3 01_health_check.py --full --max-months 6     # Только приёмки за 6 месяцев
    cd 02_checks/01_health/scripts && python3 01_health_check.py --full
"""

import sys
import os
import json
import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '_shared'))
from api_client import ProductionHelper, MOYSKLAD_TOKEN

from health_config import DEFAULT_STORES, TARGET_GROUPS, SLOT_STORES, NORMAL_MOVE_DIRECTIONS
from health_docs import DocumentChecksMixin
from health_prices import PriceChecksMixin
from health_report import ReportingMixin


class CostHealthCheck(DocumentChecksMixin, PriceChecksMixin, ReportingMixin):
    """Проверка здоровья себестоимости"""

    # Возврат-черновик старше этого срока — товар, похоже, застрял по дороге
    PENDING_RETURN_WARN_DAYS = 30

    def __init__(self, helper, threshold=5.0, supply_threshold=15.0, prev_count=3,
                 max_months=12, enter_months=3, doc_months=3,
                 inv_threshold=50, move_threshold=10000, full_mode=False):
        self.h = helper
        self.full_mode = full_mode
        self.threshold = threshold
        self.supply_threshold = supply_threshold
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
        self.salesreturn_ack_ids = self._load_ack('salesreturns_acknowledged.json')
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
            'suspect_sales_returns': [],  # Возвраты от покупателей с нулевой себестоимостью
            'enter_zero_prices': [],      # Оприходования с нулевой ценой позиций
            'enter_price_issues': [],     # Свежие оприходования с ценой, не совпадающей с приёмкой на тот момент
            'code_no_code': [],           # Товары без кода
            'code_duplicates': {},        # {code: [products]} — дублирующиеся коды
            'code_suspect': [],           # Товары с кодом-аномалией (не соответствует паттерну группы)
            'stale_drafts': [],           # Непроведённые документы старше порога [{type, doc_name, age_days}]
            'pending_returns': [],        # Возвраты-черновики, ждущие поступления товара [{doc_name, age_days, sum_rub, ...}]
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

    def _load_deviations_notes(self):
        """Загрузить объяснения FIFO-отклонений из avg_deviations_ignore.json."""
        path = os.path.join(os.path.dirname(__file__), '..', 'data', 'avg_deviations_ignore.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('notes', {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}


    def check_product(self, product_id, product_name, store_id, store_name, avg_cost=0, product_code=''):
        """Два типа проверок:
        1. FIFO-себестоимость vs последняя приёмка — разрыв балансовой цены склада.
        2. Свежие оприходования vs приёмка на тот момент — ошибки ввода цен в коррекциях.
        Возвращает кортеж (avg_result, enter_issues).
        """
        import time
        from datetime import datetime, timedelta

        try:
            time.sleep(0.2)

            # Получаем детализацию остатков по операциям
            stock_report = self.h._get("/report/byoperations/stock", {
                "filter": f"assortment=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id}",
                "limit": 100,
                "expand": "operation",
            })

            rows = stock_report.get('rows', [])

            # Фильтруем только нужный склад
            store_rows = []
            for row in rows:
                row_store_id = row.get('store', {}).get('meta', {}).get('href', '').split('/')[-1].split('?')[0]
                if row_store_id == store_id:
                    store_rows.append(row)

            if not store_rows:
                return None, []

            # Получаем все приёмки для этого товара
            time.sleep(0.2)

            turnover = self.h._get("/report/turnover/byoperations", {
                "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id};type=supply",
                "momentFrom": "2020-01-01 00:00:00",
                "momentTo": datetime.now().strftime('%Y-%m-%d 23:59:59'),
            })

            supply_rows = turnover.get('rows', [])

            if not supply_rows:
                return None, []

            # Сортируем по дате (от новых к старым)
            supply_rows.sort(key=lambda x: x.get('operation', {}).get('moment', ''), reverse=True)

            last_supply = supply_rows[0]
            last_supply_cost = last_supply.get('cost', 0) / 100
            last_supply_date = last_supply.get('operation', {}).get('moment', 'N/A')

            if last_supply_cost == 0:
                return None, []

            # Собираем номера enter-документов для отображения в статистике
            # expand=operation не всегда даёт name — подтягиваем по ID если нужно
            enter_docs = []
            _enter_id_cache = {}
            for row in store_rows:
                op = row.get('operation', {})
                if op.get('meta', {}).get('type') != 'enter':
                    continue
                doc_name = op.get('name')
                if not doc_name:
                    href = op.get('meta', {}).get('href', '')
                    doc_id = href.split('/')[-1].split('?')[0] if href else ''
                    if doc_id:
                        if doc_id not in _enter_id_cache:
                            try:
                                time.sleep(0.1)
                                doc_obj = self.h._get(f"/entity/enter/{doc_id}")
                                _enter_id_cache[doc_id] = doc_obj.get('name', f'id:{doc_id[:8]}')
                            except Exception:
                                _enter_id_cache[doc_id] = f'id:{doc_id[:8]}'
                        doc_name = _enter_id_cache[doc_id]
                    else:
                        doc_name = '?'
                if doc_name not in enter_docs:
                    enter_docs.append(doc_name)

            # ---- ПРОВЕРКА 1: Средневзвешенная vs последняя приёмка ----
            # Показывает реальный разрыв между балансовой ценой склада и текущей ценой закупки
            avg_result = None
            if avg_cost == 0:
                avg_result = {
                    'product_id': product_id,
                    'product_name': product_name,
                    'product_code': product_code,
                    'store_name': store_name,
                    'current_cost': 0,
                    'last_supply_cost': last_supply_cost,
                    'last_supply_date': last_supply_date[:10] if last_supply_date != 'N/A' else 'N/A',
                    'deviation_pct': 100,
                    'stock': sum(r.get('stock', 0) for r in store_rows),
                    'enter_docs': enter_docs,
                }
            else:
                deviation_pct = abs(avg_cost - last_supply_cost) / last_supply_cost * 100
                diff_kopecks = abs(avg_cost - last_supply_cost) * 100
                if diff_kopecks > 1.0 and deviation_pct > 0:
                    avg_result = {
                        'product_id': product_id,
                        'product_name': product_name,
                        'product_code': product_code,
                        'store_name': store_name,
                        'current_cost': avg_cost,
                        'last_supply_cost': last_supply_cost,
                        'last_supply_date': last_supply_date[:10] if last_supply_date != 'N/A' else 'N/A',
                        'deviation_pct': deviation_pct,
                        'stock': sum(r.get('stock', 0) for r in store_rows),
                        'enter_docs': enter_docs,
                    }

            # ---- ПРОВЕРКА 2: Свежие оприходования vs приёмка на тот момент ----
            # Ловит ошибки ввода: оприходование создано с неправильной ценой
            enter_issues = []
            cutoff_str = (datetime.now() - timedelta(days=self.enter_months * 30)).strftime('%Y-%m-%dT%H:%M:%S')

            for row in store_rows:
                op = row.get('operation', {})
                if op.get('meta', {}).get('type') != 'enter':
                    continue

                enter_moment = op.get('moment', '')
                cost_per_unit = row.get('costPerUnit', 0) / 100
                is_recent = bool(enter_moment and enter_moment >= cutoff_str)
                is_zero = (cost_per_unit == 0)

                # Нулевая цена проверяется всегда (любая дата)
                # Ненулевая — только для свежих оприходований
                if not is_recent and not is_zero:
                    continue

                # Находим последнюю приёмку НА МОМЕНТ создания оприходования
                supply_at_time_cost = None
                supply_at_time_date = None
                for supply in supply_rows:  # отсортированы от новых к старым
                    s_date = supply.get('operation', {}).get('moment', '')
                    if s_date <= enter_moment:
                        supply_at_time_cost = supply.get('cost', 0) / 100
                        supply_at_time_date = s_date[:10]
                        break

                if supply_at_time_cost is None or supply_at_time_cost == 0:
                    continue

                dev = abs(cost_per_unit - supply_at_time_cost) / supply_at_time_cost * 100
                diff_kop = abs(cost_per_unit - supply_at_time_cost) * 100

                if diff_kop <= 1.0 or dev < self.threshold:
                    continue

                enter_issues.append({
                    'product_id': product_id,
                    'product_name': product_name,
                    'store_name': store_name,
                    'enter_doc': op.get('name', '?'),
                    'enter_date': enter_moment[:10],
                    'enter_cost': cost_per_unit,
                    'supply_cost': supply_at_time_cost,
                    'supply_date': supply_at_time_date,
                    'deviation_pct': dev,
                })

            return avg_result, enter_issues

        except Exception as e:
            print(f"  ⚠️ Пропущен товар '{product_name}': {e}")
            return None, []

    def categorize_issue(self, result):
        """Категоризировать проблему"""
        current = result['current_cost']
        deviation = result['deviation_pct']

        # Критичные проблемы
        if current == 0:
            return 'critical', "ЦЕНА 0.00"
        if deviation > 50:
            return 'critical', f"ОГРОМНОЕ ОТКЛОНЕНИЕ {deviation:.1f}%"

        # Важные проблемы
        if deviation >= self.threshold:
            return 'important', f"Отклонение {deviation:.1f}%"

        # Всё ок
        return 'ok', f"OK (отклонение {deviation:.2f}%)"

    def check_store(self, store_id, store_name):
        """Проверить все товары на складе"""

        # Тут же, за один проход по товарам склада, разбираются два разных
        # чек-листа: FIFO-себестоимость и цены оприходований — назвать явно,
        # иначе в панели "выполняется" видно только техническое "Склад: X"
        self._section_header(f"FIFO и цены приёмок — {store_name}")

        # Получаем все товары с остатками
        rows = self.h._get_all_pages("/report/stock/all", {
            "filter": f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{store_id}",
        })
        self.stats['scanned'][store_name] = len(rows)
        print(f"  Товаров с остатками: {len(rows)}")

        found = 0
        total = len(rows)
        for i, row in enumerate(rows, 1):
            # href может содержать query (…/product/<id>?expand=supplier) — id только до '?'
            product_id = row.get('meta', {}).get('href', '').split('/')[-1].split('?')[0]
            product_name = row.get('name', 'N/A')
            product_code = row.get('code', '') or ''
            avg_cost = row.get('price', 0) / 100  # FIFO-себестоимость (взвешенная средняя по текущим партиям, в копейках)

            # Показываем что обрабатываем прямо сейчас
            name_short = product_name[:48]
            print(f"  [{i:3d}/{total}] {name_short:<48}", end='\r', flush=True)

            result, enter_issues = self.check_product(product_id, product_name, store_id, store_name, avg_cost, product_code)

            for issue in enter_issues:
                self.stats['enter_price_issues'].append(issue)

            if result:
                found += 1
                category, message = self.categorize_issue(result)

                # Понижаем critical→important если товар объяснён как "норма" в avg_deviations_ignore.json
                # (только для отклонений — нулевую цену не прощаем)
                if category == 'critical' and result.get('current_cost', 0) != 0:
                    note_entry = self.deviations_notes_map.get(result.get('product_code', ''))
                    if note_entry and note_entry.get('status') == 'норма':
                        category = 'important'
                        message = f"[объяснено] {message}"

                if category != 'ok':
                    result['message'] = message
                    # Дедупликация: если товар уже есть в другой категории или этой же —
                    # оставляем запись с наибольшим отклонением
                    existing = next(
                        (r for cat in ('critical', 'important', 'warnings')
                         for r in self.stats[cat]
                         if r['product_id'] == result['product_id']),
                        None
                    )
                    if existing is None:
                        self.stats['total'] += 1
                        self.stats[category].append(result)
                    elif result['deviation_pct'] > existing['deviation_pct']:
                        # Заменяем на худший результат
                        for cat in ('critical', 'important', 'warnings'):
                            self.stats[cat] = [r for r in self.stats[cat]
                                               if r['product_id'] != result['product_id']]
                        self.stats[category].append(result)
                else:
                    pid = result['product_id']
                    already_counted = any(
                        r['product_id'] == pid
                        for cat in ('critical', 'important', 'warnings')
                        for r in self.stats[cat]
                    )
                    if not already_counted:
                        self.stats['total'] += 1
                        self.stats['ok'] += 1

        print(f"  [{total}/{total}] Готово." + " " * 60)



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
    parser.add_argument('--supply-threshold', type=float, default=15.0,
                       help='Порог скачка цены в приёмках, %% (по умолчанию 15.0)')
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
    checker._total_checks = len(stores) + 12 + (1 if args.full else 0)

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

    # 10. Возвраты от покупателей с нулевой себестоимостью (всегда)
    try:
        checker.check_suspect_sales_returns()
    except Exception as e:
        print(f"❌ Ошибка при проверке возвратов: {e}\n")

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

    # 16. Возвраты, ждущие поступления товара (всегда)
    try:
        checker.check_pending_returns()
    except Exception as e:
        print(f"❌ Ошибка при проверке ожидающих возвратов: {e}\n")

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
