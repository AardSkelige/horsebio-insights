"""Проверки цен и кодов товаров: скачки цен в приёмках, нулевые цены оприходований,
коды товаров (отсутствие, дубли, аномалии)."""
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean

from health_config import TARGET_GROUPS


class PriceChecksMixin:
    """Проверки цен/кодов CostHealthCheck (используется как примесь)."""

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
                        'folder_name': group_name
                    })

            except Exception as e:
                print(f"  ❌ Ошибка при загрузке группы '{group_name}': {e}")

        return products

    def check_supply_price(self, product_id, product_name):
        """Проверить скачок цены в приёмках одного товара.

        Возвращает dict если скачок превышает порог, иначе None.
        """
        import time

        try:
            time.sleep(0.2)

            turnover = self.h._get("/report/turnover/byoperations", {
                "filter": f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{product_id};type=supply",
                "momentFrom": "2020-01-01 00:00:00",
                "momentTo": datetime.now().strftime('%Y-%m-%d 23:59:59'),
                "limit": 10,
            })

            rows = turnover.get('rows', [])

            if len(rows) < 2:
                return None  # Недостаточно приёмок для сравнения

            # Сортируем от новых к старым
            rows.sort(key=lambda x: x.get('operation', {}).get('moment', ''), reverse=True)

            prices = [r.get('cost', 0) / 100 for r in rows]
            qtys = [r.get('quantity', 0) for r in rows]

            # Фильтруем нулевые цены (но сохраняем соответствие с qtys)
            filtered = [(p, q) for p, q in zip(prices, qtys) if p > 0]
            if len(filtered) < 2:
                return None
            prices = [p for p, q in filtered]
            qtys = [q for p, q in filtered]

            last_price = prices[0]
            last_qty = qtys[0]

            # Берём предыдущие цены только в пределах max_months
            # чтобы старые приёмки (2021 и т.п.) не искажали среднее
            prev_candidates = []
            for r in rows[1: 1 + self.prev_count + 3]:  # +3 запас на случай пропусков
                op_moment = r.get('operation', {}).get('moment', '')[:10]
                p = r.get('cost', 0) / 100
                if p <= 0:
                    continue
                try:
                    dt = datetime.strptime(op_moment, '%Y-%m-%d')
                    if dt >= self.cutoff_date:
                        prev_candidates.append(p)
                except ValueError:
                    prev_candidates.append(p)
                if len(prev_candidates) >= self.prev_count:
                    break

            if not prev_candidates:
                return None

            prev_prices = prev_candidates
            avg_prev = mean(prev_prices)

            if avg_prev == 0:
                return None

            jump_pct = abs(last_price - avg_prev) / avg_prev * 100

            if jump_pct < self.supply_threshold:
                return None

            last_op = rows[0].get('operation', {})
            last_doc = last_op.get('name', 'N/A')
            last_date = last_op.get('moment', 'N/A')
            if last_date != 'N/A':
                last_date = last_date[:10]

            # Пропускаем если приёмка старше max_months
            if last_date != 'N/A':
                try:
                    supply_dt = datetime.strptime(last_date, '%Y-%m-%d')
                    if supply_dt < self.cutoff_date:
                        return None
                except ValueError:
                    pass

            # История последних приёмок для контекста (включая текущую)
            history = []
            for r in rows[:1 + self.prev_count]:
                op = r.get('operation', {})
                p = r.get('cost', 0) / 100
                q = r.get('quantity', 0)
                if p > 0:
                    history.append({
                        'doc': op.get('name', '?'),
                        'date': op.get('moment', '')[:10],
                        'price': p,
                        'qty': q,
                    })

            # Авто-определение паттерна "одна сторона этикетки":
            # наклейка + цена упала до 40-65% от предыдущей ≈ заказали только задник или передник
            auto_reason = None
            if product_name.startswith('Наклейка') and last_price < avg_prev:
                ratio = last_price / avg_prev
                if 0.30 <= ratio <= 0.70:
                    auto_reason = (
                        f"Авто: цена ~{ratio*100:.0f}% от предыдущей — возможно заказана"
                        f" одна сторона этикетки (задник или передник)"
                    )

            return {
                'name': product_name,
                'last_price': last_price,
                'last_qty': last_qty,
                'avg_prev': avg_prev,
                'jump_pct': jump_pct,
                'last_doc': last_doc,
                'last_date': last_date,
                'history': history,
                'auto_reason': auto_reason,
            }

        except Exception:
            return None

    def check_enter_zero_prices(self):
        """
        Проверка #14: оприходования с нулевой ценой позиций.

        Нулевая цена в оприходовании занижает FIFO-себестоимость товара — независимо от его
        типа (сырьё, ГП, тара). В отличие от существующей проверки, эта не
        требует истории приёмок и ловит ГП/тару у которых приёмок нет вообще.

        Убрать из отчёта: [ok] в описании документа или ID в enter_zero_acknowledged.json.
        """
        import time

        self._section_header(f"Оприходования с нулевой ценой позиций (последние {self.doc_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            docs = self.h._get_all_pages("/entity/enter", {
                "filter": f"moment>={date_from}",
                "order": "moment,desc",
            })
            print(f"  Оприходований за период: {len(docs)}")

            found = []
            for doc in docs:
                doc_id   = doc["id"]
                doc_name = doc.get("name", "?")
                doc_date = doc.get("moment", "")[:10]
                doc_desc = doc.get("description", "") or ""

                time.sleep(0.15)
                pos_resp = self.h._get(f"/entity/enter/{doc_id}/positions",
                                       {"expand": "assortment", "limit": 100})
                positions = pos_resp.get("rows", []) if pos_resp else []

                zero_pos = [
                    p for p in positions
                    if (p.get("price") or 0) == 0
                ]
                if not zero_pos:
                    continue
                if doc_id in self.enter_zero_ack_ids or '[ok]' in doc_desc.lower():
                    continue

                issue = {
                    "doc_name": doc_name,
                    "doc_date": doc_date,
                    "doc_id":   doc_id,
                    "doc_desc": doc_desc[:60],
                    "positions": [
                        {
                            "name": p.get("assortment", {}).get("name", "?"),
                            "qty":  p.get("quantity", 0),
                        }
                        for p in zero_pos
                    ],
                }
                found.append(issue)
                self.stats["enter_zero_prices"].append(issue)

            if not found:
                print("  ✅ Оприходований с нулевыми ценами не найдено\n")
                return

            print(f"  ❌ Найдено документов с нулевыми ценами: {len(found)}\n")
            for issue in found:
                print(f"  Оприходование №{issue['doc_name']} от {issue['doc_date']}"
                      + (f"  — {issue['doc_desc']}" if issue['doc_desc'] else ""))
                for p in issue["positions"]:
                    print(f"    ❌ {p['name'][:60]}  qty={p['qty']}")
                print()

        except Exception as e:
            print(f"  ❌ Ошибка: {e}\n")

    def check_product_codes(self):
        """
        Проверка #12: коды товаров в группах Материалы для производства, Товары, Этикетки.
        Находит: товары без кода, дубли кодов, аномальные коды (не соответствуют паттерну группы).
        """
        import re

        CODE_CHECK_GROUPS = ["Материалы для производства", "Товары", "Этикетки"]
        RE_LARGE = re.compile(r'^\d{7,}$')  # 7+ цифр — скорее всего баркод/автономер

        self._section_header("Коды товаров", f"Группы: {', '.join(CODE_CHECK_GROUPS)}")

        # Загрузить все товары (один раз)
        all_products = self.h._get_all_pages("/entity/product")
        print(f"  Всего товаров в аккаунте: {len(all_products)}")

        # Карта id товара → ссылка на карточку в UI МойСклад (id в UI ≠ API-id, берём из meta.uuidHref)
        self._product_uuid_href = {p.get('id'): (p.get('meta') or {}).get('uuidHref') for p in all_products}

        # Фильтруем по нужным группам через pathName
        target_products = []
        for p in all_products:
            path = p.get('pathName', '')
            for root in CODE_CHECK_GROUPS:
                if path == root or path.startswith(root + '/'):
                    p['_folder_path'] = path
                    target_products.append(p)
                    break

        print(f"  Товаров в целевых группах: {len(target_products)}\n")

        # Товары без кода
        no_code = [p for p in target_products if not (p.get('code') or '').strip()]

        # Карта кодов → список товаров
        code_map = defaultdict(list)
        for p in target_products:
            code = (p.get('code') or '').strip()
            if code:
                code_map[code].append(p)

        # Дубли
        duplicates = {code: plist for code, plist in code_map.items() if len(plist) > 1}

        # Аномальные коды: в группе, где большинство кодов короткие, есть длинный (баркод)
        group_codes = defaultdict(list)
        for code, plist in code_map.items():
            for p in plist:
                group_codes[p.get('_folder_path', '')].append(code)

        suspect = []
        for p in target_products:
            code = (p.get('code') or '').strip()
            if not code:
                continue
            group = p.get('_folder_path', '')
            codes_in_group = group_codes[group]
            short = [c for c in codes_in_group if not RE_LARGE.match(c)]
            large = [c for c in codes_in_group if RE_LARGE.match(c)]
            if len(short) > len(large) and RE_LARGE.match(code):
                suspect.append({'name': p.get('name', ''), 'code': code,
                                 'group': group, 'id': p.get('id', '')})

        self.stats['code_no_code'] = [
            {'name': p.get('name', ''), 'group': p.get('_folder_path', ''), 'id': p.get('id', '')}
            for p in no_code
        ]
        self.stats['code_duplicates'] = {
            code: [{'name': p.get('name', ''), 'group': p.get('_folder_path', '')} for p in plist]
            for code, plist in duplicates.items()
        }
        self.stats['code_suspect'] = suspect

        # Вывод
        if no_code:
            print(f"  ❌ Товары без кода ({len(no_code)}):")
            for p in no_code:
                print(f"     • {p.get('name', '')[:60]}  [{p.get('_folder_path', '')}]")
            print()

        if duplicates:
            print(f"  ⚠️  Дублирующиеся коды ({len(duplicates)}):")
            for code, plist in sorted(duplicates.items()):
                print(f"     Код {code!r}:")
                for p in plist:
                    print(f"       • {p.get('name', '')[:60]}  [{p.get('_folder_path', '')}]")
            print()

        if suspect:
            print(f"  ⚡ Аномальные коды ({len(suspect)}) — длинное число в группе с короткими кодами:")
            for s in suspect:
                print(f"     • {s['name'][:55]}  код: {s['code']}  [{s['group']}]")
            print()

        if not no_code and not duplicates and not suspect:
            print("  ✅ Коды товаров в порядке\n")

    def check_all_supply_prices(self):
        """Проверить скачки цен в приёмках по целевым группам товаров"""
        import json

        self._section_header(
            f"Скачки цен в приёмках",
            f"Порог {self.supply_threshold}%, среднее по {self.prev_count} пред., не старше {self.max_months} мес."
        )

        # Загружаем игнор-лист (supply_jumps_ignore.json рядом со скриптом)
        # Формат: {"ignored": [{"name": "...", "reason": "..."}]}
        ignore_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'supply_jumps_ignore.json')
        ignore_map = {}  # name -> reason
        if os.path.exists(ignore_file):
            try:
                data = json.loads(open(ignore_file, encoding='utf-8').read())
                ignore_map = {e['name']: e.get('reason', '') for e in data.get('ignored', [])}
                pass  # Игнор-лист загружен, детали — в итоговой статистике
            except Exception as e:
                print(f"  ⚠️ Не удалось загрузить игнор-лист: {e}\n")

        print("Загрузка товаров из групп:")
        products = self.get_products_by_groups()
        print(f"\nВсего товаров для проверки: {len(products)}\n")

        total = len(products)
        for i, product in enumerate(products, 1):
            name_short = product['name'][:48]
            print(f"  [{i:3d}/{total}] {name_short:<48}", end='\r', flush=True)

            result = self.check_supply_price(product['id'], product['name'])

            if result:
                reason = ignore_map.get(product['name'])
                if reason is not None:
                    # Явная запись в игнор-листе
                    result['reason'] = reason
                    self.stats['supply_jumps_explained'].append(result)
                elif result.get('auto_reason'):
                    # Авто-определённый паттерн (напр. одна сторона этикетки)
                    result['reason'] = result['auto_reason']
                    self.stats['supply_jumps_explained'].append(result)
                else:
                    self.stats['supply_jumps'].append(result)

        print(f"  [{total}/{total}] Готово." + " " * 60)
