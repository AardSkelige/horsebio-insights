from datetime import datetime, timedelta

from health_format import money


class InventoryChecksMixin:
    def check_suspect_inventories(self):
        """Найти инвентаризации с большими расхождениями или без описания за последние N месяцев.

        Флаги:
          no_desc           — нет описания
          big_diff          — сумма |correctionAmount| > inv_threshold
          no_correction_docs — есть расхождение, но correction-документы НЕ созданы
                               (остатки в системе до сих пор неправильные!)
        correctionAmount = quantity (факт) − calculatedQuantity (по системе).
        """
        import time

        self._section_header(f"Инвентаризации (последние {self.doc_months} мес., порог {self.inv_threshold} ед.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            time.sleep(0.3)
            docs = self.h._get_all_pages("/entity/inventory", {
                "filter": f"moment>={date_from}",
                "order": "moment,desc",
                "expand": "store,enters,losses",
            })
            total = len(docs)
            print(f"  Инвентаризаций за период: {total}")

            for i, doc in enumerate(docs, 1):
                doc_name = doc.get('name', '?')
                desc = (doc.get('description') or '')
                store_name = doc.get('store', {}).get('name', '?')
                print(f"    [{i:2d}/{total}] №{doc_name} ...", end='\r', flush=True)

                if doc['id'] in self.inventory_ack_ids or '[ok]' in desc.lower():
                    continue

                time.sleep(0.2)
                pos_result = self.h._get(f"/entity/inventory/{doc['id']}/positions", {
                    "limit": 1000,
                    "expand": "assortment",
                })
                positions = pos_result.get('rows', [])

                total_diff = sum(abs(p.get('correctionAmount', 0)) for p in positions)

                # Проверяем наличие связанных correction-документов
                has_enters = bool(doc.get('enters'))
                has_losses = bool(doc.get('losses'))
                has_correction_docs = has_enters or has_losses

                flags = []
                if not desc:
                    flags.append('no_desc')
                if total_diff > self.inv_threshold:
                    flags.append('big_diff')
                # Критичный флаг: расхождение есть, но документы не созданы
                if total_diff > 0 and not has_correction_docs:
                    flags.append('no_correction_docs')

                if not flags:
                    continue

                # Топ-3 позиции с наибольшим расхождением
                top_positions = sorted(
                    [p for p in positions if abs(p.get('correctionAmount', 0)) > 0],
                    key=lambda p: abs(p.get('correctionAmount', 0)),
                    reverse=True
                )[:3]

                self.stats['suspect_inventories'].append({
                    'doc_id':      doc['id'],
                    'doc_name':    doc_name,
                    'moment':      doc.get('moment', '')[:10],
                    'store':       store_name,
                    'description': desc[:120],
                    'flags':       flags,
                    'total_diff':  total_diff,
                    'top_positions': [
                        {
                            'name':       p.get('assortment', {}).get('name', '?'),
                            'correction': p.get('correctionAmount', 0),
                        }
                        for p in top_positions
                    ],
                })

            print(f"    [{total}/{total}] Готово." + " " * 40)

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

        print()

    def check_inventory_prices(self):
        """Проверить цены в позициях инвентаризаций за последний месяц.

        Цена сравнивается с FIFO за секунду до инвентаризации: новая партия законно сдвигает FIFO, и сравнение с сегодняшним давало ложные тревоги (№00071 и №00072 от 29.09.2026).
        Если FIFO на ту дату нет, потому что остаток был нулевой, сравниваем с сегодняшним.

        Оцениваем только позиции с correctionAmount > 0. Сама инвентаризация склад
        не двигает — движение делают связанные оприходование (излишки) и списание
        (недостача), а в них попадают лишь скорректированные позиции (проверено на
        №00043: enter/loss содержат ровно 7 позиций с ненулевой коррекцией из 47).
        Цена позиции без коррекции справочная и на FIFO не влияет — раньше это давало
        целый класс ложных тревог (buyPrice был верным на дату инв., FIFO упал позже).

        Недостачи тоже не оцениваем: списание МойСклад проводит по FIFO сам, цену
        из инвентаризации не берёт (№00073 от 01.10.2026: коробка 500 мл в инв. 13,13 ₽,
        в списании 00073-00001 — 16,43 ₽ по старым партиям). А сравнение с FIFO
        «на сегодня» у недостачи ложное по построению: её же списание забирает
        старые партии и сдвигает среднюю. В учёт цена идёт только у излишка —
        через оприходование, где она и становится себестоимостью.

        Флаги:
          zero_price   — price=0 (демон не отработал или не нашёл себестоимость)
          big_deviation — цена отличается от FIFO-себестоимости >30%
        """
        import time

        self._section_header("Цены в инвентаризациях (последние 30 дней)")

        date_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            # Загружаем FIFO-себестоимость
            stock_items = []
            offset = 0
            while True:
                r = self.h._get("/report/stock/all", {"limit": 1000, "offset": offset})
                rows = r.get("rows", [])
                stock_items.extend(rows)
                if len(rows) < 1000:
                    break
                offset += 1000
                time.sleep(0.2)

            stock_price_by_id = {}
            for item in stock_items:
                if item.get("meta", {}).get("type") != "product":
                    continue
                pid = item["meta"]["href"].split("/")[-1].split("?")[0]
                price = round(item.get("price", 0) or 0)
                if price > 0:
                    stock_price_by_id[pid] = price

            # Загружаем инвентаризации за период (все страницы)
            time.sleep(0.3)
            docs = self.h._get_all_pages("/entity/inventory", {
                "filter": f"moment>={date_from}",
                "order": "moment,desc",
                "expand": "store",
            })
            total = len(docs)
            print(f"  Инвентаризаций за период: {total}")

            for i, doc in enumerate(docs, 1):
                doc_name = doc.get("name", "?")
                store_name = doc.get("store", {}).get("name", "?")
                print(f"    [{i:2d}/{total}] №{doc_name} ...", end="\r", flush=True)

                if doc['id'] in self.inventory_ack_ids:
                    continue

                time.sleep(0.2)
                pos_result = self.h._get(f"/entity/inventory/{doc['id']}/positions", {
                    "limit": 1000,
                    "expand": "assortment",
                })
                positions = pos_result.get("rows", [])

                zero_positions = []
                deviation_positions = []

                # Цена идёт в учёт только у излишка (через оприходование). Позиция
                # без коррекции никуда не попадает, недостачу списание оценит по FIFO.
                surplus = [p for p in positions if (p.get("correctionAmount") or 0) > 0]
                price_on_date = self._fifo_on_date(doc.get("moment", ""), surplus) if surplus else {}

                for pos in surplus:
                    price = pos.get("price", 0) or 0
                    assortment = pos.get("assortment", {})
                    product_name = assortment.get("name", "?")
                    href = assortment.get("meta", {}).get("href", "")
                    pid = href.split("/")[-1].split("?")[0] if href else None

                    if price == 0:
                        zero_positions.append(product_name)
                        continue

                    avg = price_on_date.get(pid) or stock_price_by_id.get(pid)
                    if avg:
                        deviation = abs(price - avg) / avg * 100
                        if deviation > 30:
                            deviation_positions.append({
                                "name": product_name,
                                "price_rub": round(price / 100, 2),
                                "avg_rub": round(avg / 100, 2),
                                "deviation_pct": round(deviation, 1),
                            })

                if not zero_positions and not deviation_positions:
                    continue

                flags = []
                if zero_positions:
                    flags.append("zero_price")
                if deviation_positions:
                    flags.append("big_deviation")

                self.stats["inventory_price_issues"].append({
                    "doc_id": doc['id'],
                    "doc_name": doc_name,
                    "moment": doc.get("moment", "")[:10],
                    "store": store_name,
                    "applicable": doc.get("applicable", True),
                    "flags": flags,
                    "zero_positions": zero_positions[:5],
                    "deviation_positions": deviation_positions[:5],
                })

            print(f"    [{total}/{total}] Готово." + " " * 40)

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

        print()

    def _fifo_on_date(self, moment, positions):
        import time

        ids = []
        for pos in positions:
            href = pos.get("assortment", {}).get("meta", {}).get("href", "")
            if "/entity/product/" in href:
                ids.append(href.split("/")[-1].split("?")[0])
        if not ids or not moment:
            return {}

        before = (datetime.strptime(moment[:19], '%Y-%m-%d %H:%M:%S') - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
        prices = {}
        for start in range(0, len(ids), 40):
            filters = [f"moment={before}"] + [
                f"product=https://api.moysklad.ru/api/remap/1.2/entity/product/{pid}" for pid in ids[start:start + 40]
            ]
            time.sleep(0.2)
            try:
                rows = self.h._get("/report/stock/all", {"filter": ";".join(filters), "limit": 1000}).get("rows", [])
            except Exception as e:
                print(f"  FIFO на {before} не получен, сравниваю с сегодняшним: {e}")
                continue
            for row in rows:
                pid = row.get("meta", {}).get("href", "").split("/")[-1].split("?")[0]
                price = round(row.get("price", 0) or 0)
                if price > 0:
                    prices[pid] = price
        return prices

    def report_inventory_prices(self):
        inv_price_issues = self.stats['inventory_price_issues']
        if inv_price_issues:
            print(f"\n💰 ИНВЕНТАРИЗАЦИИ С ПРОБЛЕМАМИ ЦЕН ({len(inv_price_issues)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ zero_price: демон не отработал или товар без остатка. big_deviation: цена отличается от FIFO-себестоимости >30%")
            print("-" * 70)
            for item in inv_price_issues:
                status = "непроведена" if not item['applicable'] else "проведена"
                print(f"  🔴 №{item['doc_name']:<26}  {item['moment']}  {item['store']}  [{status}]")
                if item['zero_positions']:
                    names = ', '.join(p[:30] for p in item['zero_positions'][:5])
                    more = f" + ещё {len(item['zero_positions']) - len(item['zero_positions'][:5])}" if len(item['zero_positions']) > 5 else ""
                    print(f"      ⛔ Нулевая цена: {names}{more}")
                for p in item['deviation_positions']:
                    print(f"      ⚠️  {p['name'][:40]:<40}  {p['price_rub']:.2f} руб (FIFO: {p['avg_rub']:.2f}, откл. {p['deviation_pct']}%)")
                print()
        else:
            print(f"\n✅ Цен с проблемами в инвентаризациях не найдено (последние {self.doc_months} мес.)")

    def report_inventories(self):
        inventories = self.stats['suspect_inventories']
        if inventories:
            print(f"\n📋 ИНВЕНТАРИЗАЦИИ С РАСХОЖДЕНИЯМИ ({len(inventories)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ Порог расхождения: {self.inv_threshold} ед. суммарно по документу")
            print("-" * 70)
            for item in inventories:
                flag_labels = []
                if 'no_correction_docs' in item['flags']:
                    flag_labels.append(f"⛔ ОСТАТКИ НЕ ИСПРАВЛЕНЫ — нажать «Создать документы»!")
                if 'no_desc' in item['flags']:
                    flag_labels.append('нет описания')
                if 'big_diff' in item['flags']:
                    flag_labels.append(f"расхождение {item['total_diff']:.0f} ед.")
                marker = "🚨" if 'no_correction_docs' in item['flags'] else "🔴"
                desc_display = item['description'] or '(без описания)'
                print(f"  {marker} №{item['doc_name']:<26}  {item['moment']}  {item['store']}")
                print(f"      📝 {desc_display[:100]}")
                if item['top_positions']:
                    parts = [
                        f"{p['name'][:22]} ({p['correction']:+.0f})"
                        for p in item['top_positions']
                    ]
                    print(f"      ± {', '.join(parts)}")
                for label in flag_labels:
                    print(f"      ⚠️ {label}")
                print()
        else:
            print(f"\n✅ Инвентаризаций с расхождениями не найдено (последние {self.doc_months} мес.)")

    def summary_inventories(self):
        print(f"  📋 Инвентаризаций с расхождениями: {len(self.stats['suspect_inventories'])}")

    def summary_inventory_prices(self):
        inv_price_issues = self.stats['inventory_price_issues']
        if inv_price_issues:
            zero_cnt = sum(1 for i in inv_price_issues if 'zero_price' in i['flags'])
            dev_cnt = sum(1 for i in inv_price_issues if 'big_deviation' in i['flags'])
            print(f"  💰 Инвентаризаций с проблемами цен: {len(inv_price_issues)} "
                  f"(нулевые: {zero_cnt}, отклонение >30%: {dev_cnt})")
        else:
            print(f"  ✅ Цены в инвентаризациях — всё в порядке")

    def export_inventories(self, add):
        add('suspect_inventories', 'Инвентаризации с расхождениями', 'inventories', 'inventory', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}",
                'severity': 'critical' if 'no_correction_docs' in it['flags'] else 'important',
                'detail': f"{it['moment']} · {it['store']} · расхождение {it.get('total_diff', 0):.0f} ед"
                          + (' · ⛔ остатки не исправлены' if 'no_correction_docs' in it['flags'] else ''),
            }
            for it in self.stats['suspect_inventories']
        ])

    def export_inventory_prices(self, add):
        def _inv_price_detail(it):
            parts = [it['moment'], it['store']]
            zp = it.get('zero_positions') or []
            if zp:
                parts.append('цена 0: ' + ', '.join(n[:40] for n in zp[:2])
                             + (f' и ещё {len(zp) - 2}' if len(zp) > 2 else ''))
            dp = it.get('deviation_positions') or []
            for d in dp[:2]:
                parts.append(f"{d['name'][:40]}: в инв. {money(d['price_rub'])} ↔ "
                             f"FIFO {money(d['avg_rub'])} ({d['deviation_pct']:.0f}%)")
            if len(dp) > 2:
                parts.append(f'и ещё {len(dp) - 2}')
            return ' · '.join(parts)

        add('inventory_price_issues', 'Инвентаризации: проблемы цен', 'inventories', 'inventory', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}",
                'severity': 'critical' if 'zero_price' in it['flags'] else 'important',
                'detail': _inv_price_detail(it),
            }
            for it in self.stats['inventory_price_issues']
        ])
