import os
from datetime import datetime
from statistics import median
from health_config import TARGET_GROUPS
from health_format import money


class SupplyJumpChecksMixin:
    def get_products_by_groups(self):
        """Получить товары из целевых групп.

        Используем filter=pathName~=<name> — поле productFolder не фильтруется по API,
        а pathName поддерживает оператор ~= (starts with).
        """
        import time

        products = []

        for group_name in TARGET_GROUPS:
            try:
                offset = 0
                limit = 1000
                group_products = []

                while True:
                    time.sleep(0.2)
                    resp = self.h._get("/entity/product", {
                        "filter": f"pathName~={group_name}",
                        "limit": limit,
                        "offset": offset
                    })
                    batch = resp.get('rows', [])
                    group_products.extend(batch)

                    if len(batch) < limit:
                        break
                    offset += limit

                print(f"  Группа '{group_name}': {len(group_products)} товаров")

                for p in group_products:
                    products.append({
                        'id': p.get('id'),
                        'name': p.get('name', 'N/A'),
                        'code': (p.get('code') or '').strip(),
                        'folder_name': group_name
                    })

            except Exception as e:
                print(f"  ❌ Ошибка при загрузке группы '{group_name}': {e}")

        return products

    @staticmethod
    def _short_agent(row):
        """Короткое имя поставщика: «ООО "Ревада-Нева", г. Москва» → «Ревада-Нева»."""
        name = (row.get('operation', {}).get('agent', {}) or {}).get('name', '') or ''
        name = name.split(',')[0].strip()
        for prefix in ('ООО', 'АО', 'ЗАО', 'ПАО', 'ИП'):
            if name.startswith(prefix + ' '):
                name = name[len(prefix) + 1:]
        return name.replace('"', '').replace('«', '').replace('»', '').strip()

    SUPPLY_MULTIPLE = 3.0

    # Строка приёмки дешевле основной примерно вдвое — заказана одна сторона
    # этикетки, а не комплект. Границы с запасом на округление копеек.
    HALF_LINE_MIN = 0.40

    HALF_LINE_MAX = 0.60

    @classmethod
    def _merge_supply_rows(cls, rows):
        """Склеить строки одной приёмки в одну, цена — средневзвешенная по количеству.

        Один товар может стоять в приёмке несколькими строками с разной ценой
        (например комплект наклейки и отдельно задник к нему). Без склейки каждая
        строка считается самостоятельной приёмкой: одна попадает в «последнюю
        цену», другая в среднее по предыдущим — и получается скачок на пустом месте.

        Исключение — «половинная» строка: если дешёвая строка стоит 40-60% от
        дорогой, это одна сторона этикетки, а не другая цена товара. Средневзвешенная
        размывала бы цену комплекта (150 шт по 16.40 + 120 шт по 8.20 → 12.76) и
        давала ложный скачок, поэтому ценой документа берём дорогую строку.

        Возвращает строки от новых к старым.
        """
        merged = {}
        for r in rows:
            op = r.get('operation', {})
            key = op.get('meta', {}).get('href') or op.get('name')
            if not key:
                continue  # без опознанного документа склеивать не с чем
            qty = r.get('quantity', 0) or 0
            sum_cost = r.get('sum', 0) or 0  # итог строки в копейках
            item = merged.get(key)
            if item is None:
                merged[key] = {'operation': op, 'quantity': qty, 'sum_cost': sum_cost,
                               'units': []}
                item = merged[key]
            else:
                item['quantity'] += qty
                item['sum_cost'] += sum_cost
            if qty:
                item['units'].append(sum_cost / qty)

        rows = [
            {
                'operation': it['operation'],
                'quantity': it['quantity'],
                'cost': cls._doc_unit_cost(it),
            }
            for it in merged.values()
        ]
        rows.sort(key=lambda x: x['operation'].get('moment', ''), reverse=True)
        return rows

    @classmethod
    def _doc_unit_cost(cls, item):
        """Цена товара в документе: средневзвешенная, но без «половинных» строк."""
        units = item['units']
        if len(units) > 1:
            full = max(units)
            if full and cls.HALF_LINE_MIN <= min(units) / full <= cls.HALF_LINE_MAX:
                return full
        qty = item['quantity']
        return item['sum_cost'] / qty if qty else 0

    def check_supply_price(self, product_id, product_name, sheet_docs=None):
        """Проверить скачок цены в приёмках одного товара.

        Возвращает dict если скачок превышает порог, иначе None.
        """
        import time

        try:
            time.sleep(0.2)

            # momentFrom = cutoff_date, а не 2020 год: отчёт отдаёт строки от старых
            # к новым и режет по limit, поэтому запрос за всю историю возвращал
            # приёмки 2020-2023 и до свежих не доходил — товары с длинной историей
            # выпадали из проверки целиком. Окно и так ограничено max_months.
            params = {
                "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id};type=supply",
                "momentFrom": self.cutoff_date.strftime('%Y-%m-%d 00:00:00'),
                "momentTo": datetime.now().strftime('%Y-%m-%d 23:59:59'),
                "limit": 1000,  # максимум страницы отчёта
            }

            # Забираем все строки окна: порядок выдачи не гарантирован, а одна приёмка
            # даёт несколько строк (разные цены позиций, разные склады) — неполный
            # набор исказил бы и склейку, и «последнюю» цену.
            rows = []
            offset = 0
            while True:
                turnover = self.h._get("/report/turnover/byoperations",
                                       {**params, "offset": offset})
                batch = turnover.get('rows', [])
                rows.extend(batch)
                offset += len(batch)
                size = turnover.get('meta', {}).get('size', len(rows))
                if not batch or offset >= size:
                    break
                time.sleep(0.2)

            is_label = product_name.startswith('Наклейка')
            if sheet_docs is not None and is_label:
                for r in rows:
                    op = r.get('operation', {})
                    href = op.get('meta', {}).get('href')
                    if href and self._is_sheet_priced(r):
                        sheet_docs.setdefault(href, {'name': op.get('name', 'N/A'), 'moment': op.get('moment', ''),
                                                     'agent': self._short_agent(r)})

            # Строки одной приёмки склеиваем, иначе каждая считается отдельной приёмкой
            rows = self._merge_supply_rows(rows)
            if not rows:
                return None

            # Последнюю приёмку наклеек от типографии проверяет сверка с листом
            if is_label and self._is_sheet_priced(rows[0]):
                return None

            last_op = rows[0].get('operation', {})
            last_date = last_op.get('moment', '')[:10]
            if last_date and datetime.strptime(last_date, '%Y-%m-%d') < self.cutoff_date:
                return None

            last_price = rows[0].get('cost', 0) / 100
            last_qty = rows[0].get('quantity', 0)
            last_agent = self._short_agent(rows[0])
            prev = [r for r in rows[1:] if r.get('cost', 0) > 0]

            # Флаг только на цену 0, разницу в разы и заметное изменение у того же поставщика
            if last_price <= 0:
                ref, basis, ref_rows = 0.0, 'zero', []
            else:
                if not prev:
                    return None
                ref_rows = prev[:self.prev_count]
                med = median(r['cost'] / 100 for r in ref_rows)
                ratio = last_price / med
                if ratio >= self.SUPPLY_MULTIPLE or ratio <= 1 / self.SUPPLY_MULTIPLE:
                    ref, basis = med, 'multiple'
                else:
                    same = [r for r in prev if self._short_agent(r) == last_agent] if last_agent else []
                    if not same:
                        return None
                    ref, basis, ref_rows = same[0]['cost'] / 100, 'same_agent', same[:1]
                    if abs(last_price - ref) / ref * 100 < self.supply_threshold:
                        return None
                    if abs(last_price - ref) * last_qty < self.supply_min_rub:
                        return None
            jump_pct = abs(last_price - ref) / ref * 100 if ref else 100.0

            history = []
            for r in rows[:1 + self.prev_count]:
                op = r.get('operation', {})
                history.append({
                    'doc': op.get('name', '?'),
                    'date': op.get('moment', '')[:10],
                    'price': r.get('cost', 0) / 100,
                    'qty': r.get('quantity', 0),
                    'agent': self._short_agent(r),
                })

            # Одна сторона наклейки у поставщика с поштучной ценой стоит примерно вдвое дешевле
            auto_reason = None
            if (basis == 'same_agent' and product_name.startswith('Наклейка')
                    and last_price < ref and 0.30 <= last_price / ref <= 0.70):
                auto_reason = (
                    f"Авто: цена ~{last_price / ref * 100:.0f}% от предыдущей — возможно заказана"
                    f" одна сторона этикетки (задник или передник)"
                )

            return {
                'name': product_name,
                'basis': basis,
                'last_price': last_price,
                'last_qty': last_qty,
                'last_agent': last_agent,
                'prev_agents': list(dict.fromkeys(a for a in (self._short_agent(r) for r in ref_rows) if a)),
                'avg_prev': ref,
                'jump_pct': jump_pct,
                'last_doc': last_op.get('name', 'N/A'),
                'last_date': last_date or 'N/A',
                'history': history,
                'auto_reason': auto_reason,
            }

        except Exception:
            return None

    def check_all_supply_prices(self):
        """Проверить скачки цен в приёмках по целевым группам товаров"""
        import json

        self._section_header(
            f"Скачки цен в приёмках",
            f"Тот же поставщик: от {self.supply_threshold:.0f}% и от {self.supply_min_rub:,.0f} ₽ на приёмку; "
            f"в {self.SUPPLY_MULTIPLE:g} раза к медиане {self.prev_count} пред.; цена 0; наклейки по листу. "
            f"Окно {self.max_months} мес."
        )

        # Загружаем игнор-лист (supply_jumps_ignore.json рядом со скриптом)
        # Формат: {"ignored": [{"key": "4-104", "name": "...", "reason": "...", "supply_doc": "00096"?}]}
        # supply_doc указан → разовое исключение: глушит только скачок, чья последняя
        # приёмка совпадает; новая приёмка с новым скачком снова попадёт в отчёт.
        # supply_doc нет → вечное («у товара всегда так»).
        # Ключ это код товара, чтобы исключение переживало переименование
        ignore_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'supply_jumps_ignore.json')
        ignore_map = {}  # key -> {'reason': ..., 'supply_doc': ...}
        if os.path.exists(ignore_file):
            try:
                data = json.loads(open(ignore_file, encoding='utf-8').read())
                ignore_map = {e['key']: e for e in data.get('ignored', []) if e.get('key')}
                pass  # Игнор-лист загружен, детали — в итоговой статистике
            except Exception as e:
                print(f"  ⚠️ Не удалось загрузить игнор-лист: {e}\n")

        print("Загрузка товаров из групп:")
        products = self.get_products_by_groups()
        print(f"\nВсего товаров для проверки: {len(products)}\n")

        total = len(products)
        found, sheet_docs = [], {}
        for i, product in enumerate(products, 1):
            name_short = product['name'][:48]
            print(f"  [{i:3d}/{total}] {name_short:<48}", end='\r', flush=True)

            result = self.check_supply_price(product['id'], product['name'], sheet_docs)
            if result:
                result['code'] = product['code']
                found.append(result)

        found.extend(self.check_sheet_prices(sheet_docs))
        for result in found:
            entry = ignore_map.get(result['code'] or result['name'])
            ignored = entry is not None and (
                not entry.get('supply_doc')                          # вечное
                or entry['supply_doc'] == result.get('last_doc'))    # разовое: та же приёмка
            if ignored:
                result['reason'] = entry.get('reason', '')
                self.stats['supply_jumps_explained'].append(result)
            elif result.get('auto_reason'):
                # Авто-определённый паттерн (напр. одна сторона этикетки)
                result['reason'] = result['auto_reason']
                self.stats['supply_jumps_explained'].append(result)
            else:
                self.stats['supply_jumps'].append(result)

        print(f"  [{total}/{total}] Готово." + " " * 60)

    def report_supply_jumps(self):
        if self.stats['supply_jumps']:
            print(f"\n📦 СКАЧКИ ЦЕН В ПРИЁМКАХ ({len(self.stats['supply_jumps'])}):")
            print("-" * 70)
            for item in sorted(self.stats['supply_jumps'], key=lambda x: x['jump_pct'], reverse=True):
                if item.get('basis') == 'zero':
                    print(f"  {item['name']}  цена 0, приёмка №{item['last_doc']} {item['last_date']}\n")
                    continue
                if item.get('basis') == 'sheet':
                    print(f"  {item['name']}  цена {item['last_price']:.2f} не раскладывается на лист "
                          f"{item['sheet_price']:.2f}, приёмка №{item['last_doc']} {item['last_date']}\n")
                    continue
                # Заголовок товара
                direction = "▲" if item['last_price'] > item['avg_prev'] else "▼"
                print(
                    f"  {item['name']}  "
                    f"{direction} {item['jump_pct']:>5.1f}%"
                )
                # История приёмок: последняя + предыдущие
                history = item.get('history', [])
                for i, h in enumerate(history):
                    qty_str = f"{h['qty']:,.0f}" if h['qty'] >= 1 else f"{h['qty']:.3f}"
                    marker = "→" if i == 0 else "  "
                    print(
                        f"    {marker} №{h['doc']:<8}  {h['date']}  "
                        f"{h['price']:>10.2f} руб  x{qty_str:<9}  {h.get('agent', '')}"
                    )
                print()

    def summary_supply_jumps(self):
        new_jumps = len(self.stats['supply_jumps'])
        explained = len(self.stats['supply_jumps_explained'])
        if new_jumps:
            print(f"  📦 Скачков цен в приёмках: {new_jumps}  ← требуют проверки")
        elif explained:
            print(f"  ✅ Скачков цен в приёмках: 0  ({explained} в игнор-листе — известные позиции)")
        else:
            print(f"  ✅ Скачков цен в приёмках: 0")

    def export_supply_jumps(self, add):
        # last_doc нужен странице для разового исключения по одной приёмке
        def _jump_detail(it):
            doc = f"приёмка №{it.get('last_doc', '?')} {it.get('last_date', '')}"
            agent = it.get('last_agent') or ''
            basis = it.get('basis')
            if basis == 'zero':
                return f"цена 0 · {doc} · {agent}"
            if basis == 'sheet':
                others = it.get('other_docs') or []
                tail = f" · ещё в приёмках №{', '.join(others)}" if others else ''
                return (f"цена {money(it['last_price'])} не раскладывается на лист "
                        f"{money(it.get('sheet_price'))} · строк в приёмке "
                        f"{it.get('lines_in_doc', 0)} · {doc} · {agent}{tail}")
            side = 'дороже' if it['last_price'] > it['avg_prev'] else 'дешевле'
            if basis == 'multiple':
                hi, lo = sorted((it['last_price'], it['avg_prev']), reverse=True)
                ratio = hi / lo if lo else 0
                prev_who = ', '.join(it.get('prev_agents') or [])
                return (f"в {ratio:.1f} раза {side} прошлых приёмок · "
                        f"последняя {money(it['last_price'])} ({agent}) ↔ медиана "
                        f"{money(it['avg_prev'])}{f' ({prev_who})' if prev_who else ''} · {doc}")
            delta = abs(it['last_price'] - it['avg_prev']) * (it.get('last_qty') or 0)
            return (f"у того же поставщика {side} на {it['jump_pct']:.0f}% · "
                    f"{money(it['avg_prev'])} → {money(it['last_price'])} · "
                    f"на приёмку {delta:,.0f} ₽ · {doc} · {agent}")

        add('supply_jumps', 'Скачки цен в приёмках', 'supply_jumps', None, [
            {
                'key': it.get('code') or it['name'], 'ms_id': '',
                'object': it['name'], 'severity': 'warning',
                'last_doc': it.get('last_doc', ''),
                'detail': _jump_detail(it),
            }
            for it in self.stats['supply_jumps']
        ])
