import os
import json

from health_format import money


class FifoChecksMixin:
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

            supply_rows = self.h._get_all_pages("/report/turnover/byoperations", {
                "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id};type=supply",
                "momentFrom": "2020-01-01 00:00:00",
                "momentTo": datetime.now().strftime('%Y-%m-%d 23:59:59'),
            })

            if not supply_rows:
                return None, []

            # Сортируем по дате (от новых к старым)
            supply_rows.sort(key=lambda x: x.get('operation', {}).get('moment', ''), reverse=True)

            last_supply = supply_rows[0]
            last_supply_cost = last_supply.get('cost', 0) / 100

            # Смесь партий не выходит за разброс закупочных цен, поэтому флаг только снаружи
            range_from = (datetime.now() - timedelta(days=self.FIFO_RANGE_MONTHS * 30)).strftime('%Y-%m-%d')
            window_costs = [r.get('cost', 0) / 100 for r in supply_rows
                            if r.get('operation', {}).get('moment', '')[:10] >= range_from
                            and r.get('cost', 0) > 0] or [last_supply_cost]
            supply_min, supply_max = min(window_costs), max(window_costs)
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
                        'supply_min': supply_min,
                        'supply_max': supply_max,
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

    FIFO_RANGE_MONTHS = 24

    @staticmethod
    def _within_supply_range(result):
        lo, hi = result.get('supply_min'), result.get('supply_max')
        if lo is None or hi is None:
            return False
        cost = result['current_cost']
        return lo * 0.99 - 0.01 <= cost <= hi * 1.01 + 0.01

    def categorize_issue(self, result):
        """Категоризировать проблему"""
        current = result['current_cost']
        deviation = result['deviation_pct']

        if current == 0:
            return 'critical', "ЦЕНА 0.00"
        if self._within_supply_range(result):
            return 'ok', f"OK (FIFO в пределах закупочных цен, отклонение {deviation:.2f}%)"
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

    def report_fifo(self):
        # Критичные проблемы
        if self.stats['critical']:
            print(f"❌ КРИТИЧНЫЕ ПРОБЛЕМЫ ({len(self.stats['critical'])}):")
            print("-" * 70)
            for item in self.stats['critical']:
                article_str = f"  код: {item['product_code']}" if item.get('product_code') else ''
                print(f"  {item['product_name']}{article_str}")
                print(f"    Склад: {item['store_name']}")
                print(f"    Проблема: {item['message']}")
                print(f"    FIFO-себест.:    {item['current_cost']:.4f} руб")
                print(f"    Последняя приёмка: {item['last_supply_cost']:.4f} руб ({item['last_supply_date']})")
                print()

        # Важные проблемы
        if self.stats['important']:
            # Разделяем на необъяснённые и объяснённые (статус "норма")
            _notes_map = self.deviations_notes_map
            _unknown   = [i for i in self.stats['important'] if not self._is_normal_deviation(i)]
            _explained = [i for i in self.stats['important'] if self._is_normal_deviation(i)]

            # Ширины колонок таблицы
            W_CODE  = 7
            W_NAME  = 42
            W_FIFO  = 9
            W_SUPP  = 9
            W_DEV   = 7
            W_STOCK = 12
            W_SEP   = W_CODE + 2 + W_NAME + 2 + W_FIFO + 2 + W_SUPP + 2 + W_DEV + 2 + W_STOCK
            note_indent = "  " + " " * (W_CODE + 2)

            if _unknown:
                print(f"\n⚠️  ВАЖНЫЕ ПРОБЛЕМЫ — FIFO vs приёмка ({len(_unknown)}):")
                print(f"  {'Код':<{W_CODE}}  {'Товар':<{W_NAME}}  "
                      f"{'FIFO':>{W_FIFO}}  {'Приёмка':>{W_SUPP}}  "
                      f"{'Δ%':>{W_DEV}}  {'Запас':<{W_STOCK}}")
                print("  " + "─" * W_SEP)

                for item in _unknown:
                    fifo      = item['current_cost']
                    supply    = item['last_supply_cost']
                    stock     = item.get('stock', 0)
                    code      = (item.get('product_code') or '')[:W_CODE]
                    raw_name  = item['product_name']
                    name      = raw_name[:W_NAME - 1] + '…' if len(raw_name) > W_NAME else raw_name
                    dev_sign  = '+' if fifo > supply else '-'
                    dev_str   = f"{dev_sign}{item['deviation_pct']:.1f}%"
                    print(f"  {code:<{W_CODE}}  {name:<{W_NAME}}  "
                          f"{fifo:.2f}р{' ':>{W_FIFO - len(f'{fifo:.2f}р')}}  "
                          f"{supply:.2f}р{' ':>{W_SUPP - len(f'{supply:.2f}р')}}  "
                          f"{dev_str:>{W_DEV}}  {stock:,.0f} ед")
                    note = _notes_map.get(item.get('product_code', ''))
                    if note:
                        status = note.get('status', '')
                        icon = {'исправлено': '🔧', 'ошибка-некритично': '⚠️'}.get(status, 'ℹ️')
                        print(f"{note_indent}{icon} {note['note']}")
                    print()

            if _explained:
                codes_str = ', '.join(i.get('product_code', '?') for i in _explained)
                print(f"\n✅ Объяснённые отклонения FIFO ({len(_explained)}) — норма, не требуют действий: {codes_str}")

    def report_enter_prices(self):
        if self.stats['enter_price_issues']:
            issues = self.stats['enter_price_issues']
            zero_issues = [i for i in issues if i['enter_cost'] == 0]
            price_issues = [i for i in issues if i['enter_cost'] != 0]

            print(f"\n🔧 ОПРИХОДОВАНИЯ С НЕПРАВИЛЬНОЙ ЦЕНОЙ ({len(issues)}):")
            print(f"   ↳ Цена в оприходовании не совпадает с приёмкой на тот момент → скорее всего ошибка ввода")
            print("-" * 70)

            if zero_issues:
                print(f"  ❌ Нулевая цена ({len(zero_issues)}) — разрушает себестоимость:")
                for item in zero_issues:
                    print(f"    • {item['product_name'][:50]}")
                    print(f"      Оприходование №{item['enter_doc']} от {item['enter_date']}: цена 0.00")
                    print(f"      Последняя приёмка на тот момент ({item['supply_date']}): {item['supply_cost']:.4f} руб")

            if price_issues:
                print(f"  ⚠️  Неверная цена ({len(price_issues)}) — проверь документы:")
                for item in price_issues:
                    direction = "дешевле" if item['enter_cost'] < item['supply_cost'] else "дороже"
                    print(f"    • {item['product_name'][:50]}  {item['deviation_pct']:>6.1f}%")
                    print(f"      Оприход. №{item['enter_doc']} ({item['enter_date']}): {item['enter_cost']:.4f} руб")
                    print(f"      Приёмка на тот момент ({item['supply_date']}):    {item['supply_cost']:.4f} руб  [{direction}]")

    def summary_fifo(self):
        scanned = self.stats['scanned']
        if scanned:
            total_scanned = sum(scanned.values())
            stores_str = ', '.join(f"{name.split()[0]}: {n}" for name, n in scanned.items())
            print(f"  Отсканировано товаров на складах: {total_scanned}  ({stores_str})")
        else:
            print(f"  Всего проверено: {self.stats['total']}")
        has_cost_issues = self.stats['critical'] or self.stats['important']
        if has_cost_issues:
            print(f"  ❌ Критичные (FIFO vs приёмка): {len(self.stats['critical'])}")
            print(f"  ⚠️  Важные (FIFO vs приёмка): {len(self.stats['important'])}")
        else:
            print(f"  ✅ FIFO-себестоимость близка к ценам приёмок — отклонений не найдено")

    def summary_enter_prices(self):
        enter_issues_cnt = len(self.stats['enter_price_issues'])
        if enter_issues_cnt:
            zero_cnt = sum(1 for i in self.stats['enter_price_issues'] if i['enter_cost'] == 0)
            print(f"  🔧 Оприходования с неправильной ценой: {enter_issues_cnt} (нулевых: {zero_cnt})")
        else:
            print(f"  ✅ Свежих оприходований с неправильной ценой не найдено")

    def _is_normal_deviation(self, it):
        # Норма действует, пока отклонение не выросло в 1,5 раза плюс 2 п.п. с момента разбора
        note = self.deviations_notes_map.get(it.get('product_code', ''), {})
        if note.get('status') != 'норма':
            return False
        ref = note.get('deviation_pct')
        if ref:
            try:
                if abs(it['deviation_pct']) > abs(float(ref)) * 1.5 + 2:
                    return False
            except (TypeError, ValueError):
                pass
        return True

    def export_fifo(self, add):
        # Позиции, помеченные «норма» (исключение), не исчезают из отчёта по логике скрипта —
        # выносим их в отдельную тихую группу, чтобы «Критичные/Важные» показывали только то,
        # что реально требует внимания.
        _notes = self.deviations_notes_map
        _phref = getattr(self, '_product_uuid_href', {})

        def _dev_item(it, sev, normal):
            # Словами, а не знаком: «+12%» читается как «подорожало», хотя означает
            # «остаток на складе числится дороже, чем стоила последняя закупка».
            side = 'склад дороже' if it['current_cost'] > it['last_supply_cost'] else 'склад дешевле'
            msg = it.get('message')
            head = (f"{msg} · " if (sev == 'critical' and msg)
                    else f"{side} закупки на {it['deviation_pct']:.1f}% · ")
            return {
                'key': it.get('product_code') or '', 'ms_id': it.get('product_id') or '',
                'ms_href': _phref.get(it.get('product_id')) or '',
                'object': it['product_name'], 'severity': sev,
                # deviation_pct нужен UI: запоминается в исключении при разборе,
                # чтобы снова флагать позицию, когда отклонение вырастет
                'deviation_pct': round(it.get('deviation_pct', 0), 1),
                # Норма есть, но отклонение с тех пор выросло, UI предложит подтвердить заново
                'stale': (_notes.get(it.get('product_code', ''), {}).get('status') == 'норма'
                          and not normal),
                'detail': head + f"{it['store_name']} · FIFO {money(it['current_cost'])} ↔ "
                          f"приёмка {money(it['last_supply_cost'])} · запас {it.get('stock', 0):,.0f} ед",
            }

        # ms_type=None: ссылка на товар только через uuidHref (ms_href) — UI-id ≠ API-id,
        # fallback #good/edit?id=<api id> всегда ведёт на «Объект не найден»
        add('critical', 'Критичные: FIFO vs приёмка', 'deviations', None,
            [_dev_item(it, 'critical', False) for it in self.stats['critical'] if not self._is_normal_deviation(it)])
        add('important', 'Важные: отклонения FIFO vs приёмка', 'deviations', None,
            [_dev_item(it, 'important', False) for it in self.stats['important'] if not self._is_normal_deviation(it)])
        add('deviations_normal', 'Отклонения, разобранные как норма', 'deviations', None,
            [_dev_item(it, 'ok', True) for it in (self.stats['critical'] + self.stats['important'])
             if self._is_normal_deviation(it)])

    def export_enter_prices(self, add):
        add('enter_price_issues', 'Оприходования с неправильной ценой', None, None, [
            {
                'key': '', 'ms_id': '',
                'object': it['product_name'],
                'severity': 'critical' if it['enter_cost'] == 0 else 'important',
                'detail': f"№{it['enter_doc']} {it['enter_date']}: {money(it['enter_cost'])} ↔ "
                          f"приёмка {money(it['supply_cost'])} ({it['supply_date']}, {it['deviation_pct']:.1f}%)",
            }
            for it in self.stats['enter_price_issues']
        ])
