from collections import defaultdict
from datetime import datetime, timedelta


class CodeChecksMixin:
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
