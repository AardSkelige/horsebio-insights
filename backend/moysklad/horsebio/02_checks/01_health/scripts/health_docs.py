"""Проверки документов МойСклад: остатки, оприходования, списания, инвентаризации,
перемещения, приёмки, возвраты, зависшие черновики."""
import json
from collections import defaultdict
from datetime import datetime, timedelta

from health_config import DEFAULT_STORES, SLOT_STORES, NORMAL_MOVE_DIRECTIONS


class DocumentChecksMixin:
    """Проверки документов CostHealthCheck (используется как примесь)."""

    def check_negative_stock(self):
        """Проверить отрицательные остатки по всем складам"""
        import time

        self._section_header("Отрицательные остатки")

        for store_id, store_name in DEFAULT_STORES.items():
            try:
                time.sleep(0.3)
                rows = self.h._get_all_pages("/report/stock/all", {
                    "filter": f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{store_id}",
                })
                negatives_found = 0

                for row in rows:
                    # Используем 'stock' (физический остаток), а не 'quantity' (доступно = остаток − резерв)
                    physical = row.get('stock', 0)
                    if physical < 0:
                        self.stats['negative_stock'].append({
                            'name': row.get('name', 'N/A'),
                            'store': store_name,
                            'qty': physical
                        })
                        negatives_found += 1

                print(f"  {store_name}: {negatives_found} отрицательных остатков")

            except Exception as e:
                print(f"  ❌ Ошибка при проверке склада {store_name}: {e}")

        print()

    def check_suspect_enters(self):
        """Найти проведённые оприходования на внутренних складах за последние N месяцев.

        Оприходование на Шатл/Производстве — сигнал: возможно должно быть перемещение.
        Исключение: документы с описанием начинающимся на "Авто:" (законные авто-корректировки).
        Дополнительно: для адресных складов (SLOT_STORES) ставит флаг no_slot если ячейка не указана.
        """
        import time

        self._section_header(f"Оприходования на внутренних складах (последние {self.enter_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.enter_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        for store_id, store_name in DEFAULT_STORES.items():
            try:
                time.sleep(0.3)
                docs = self.h._get_all_pages("/entity/enter", {
                    "filter": (
                        f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{store_id}"
                        f";moment>={date_from}"
                    ),
                    "order": "moment,desc",
                })
                applicable = [d for d in docs if d.get('applicable', False)]

                print(f"  {store_name}: {len(applicable)} проведённых")

                for doc in applicable:
                    doc_name = doc.get('name', '?')
                    desc = (doc.get('description') or '')

                    # Пропускаем подтверждённые: в JSON или маркер [ok] в описании
                    if doc['id'] in self.ack_ids or '[ok]' in desc.lower():
                        continue

                    time.sleep(0.2)
                    pos_result = self.h._get(f"/entity/enter/{doc['id']}/positions", {
                        "limit": 100,
                        "expand": "assortment",
                    })
                    positions = pos_result.get('rows', [])

                    no_slot = store_id in SLOT_STORES and any(p.get('slot') is None for p in positions)

                    self.stats['suspect_enters'].append({
                        'doc_id':      doc['id'],
                        'doc_name':    doc_name,
                        'moment':      doc.get('moment', '')[:10],
                        'store':       store_name,
                        'description': desc[:120],
                        'is_auto':     desc.startswith('Авто'),
                        'no_slot':     no_slot,
                        'is_slot_store': store_id in SLOT_STORES,
                        'positions': [
                            {
                                'name':     p.get('assortment', {}).get('name', '?'),
                                'qty':      p.get('quantity', 0),
                                'price':    p.get('price', 0) / 100,
                                'has_slot': p.get('slot') is not None,
                            }
                            for p in positions
                        ],
                    })

            except Exception as e:
                print(f"  ❌ Ошибка при проверке {store_name}: {e}")

        print()

    def check_suspect_losses(self):
        """Найти проведённые списания на внутренних складах за последние N месяцев.

        Флаги: no_desc (нет описания), zero_price (цена 0 в позиции),
               no_slot (списание с адресного склада Шатл без указания ячейки).
        Исключение: документы с [ok] в описании или в losses_acknowledged.json.
        """
        import time

        self._section_header(f"Списания на внутренних складах (последние {self.doc_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        for store_id, store_name in DEFAULT_STORES.items():
            try:
                time.sleep(0.3)
                docs = self.h._get_all_pages("/entity/loss", {
                    "filter": (
                        f"store=https://api.moysklad.ru/api/remap/1.2/entity/store/{store_id}"
                        f";moment>={date_from}"
                    ),
                    "order": "moment,desc",
                })
                applicable = [d for d in docs if d.get('applicable', False)]

                total = len(applicable)
                print(f"  {store_name}: {total} проведённых")

                for i, doc in enumerate(applicable, 1):
                    doc_name = doc.get('name', '?')
                    desc = (doc.get('description') or '')
                    print(f"    [{i:2d}/{total}] №{doc_name} ...", end='\r', flush=True)

                    if doc['id'] in self.loss_ack_ids or '[ok]' in desc.lower():
                        continue

                    time.sleep(0.2)
                    pos_result = self.h._get(f"/entity/loss/{doc['id']}/positions", {
                        "limit": 100,
                        "expand": "assortment",
                    })
                    positions = pos_result.get('rows', [])

                    flags = []
                    if not desc:
                        flags.append('no_desc')
                    if any(p.get('price', 1) == 0 for p in positions):
                        flags.append('zero_price')
                    if store_id in SLOT_STORES:
                        if any(p.get('slot') is None for p in positions):
                            flags.append('no_slot')

                    if not flags:
                        continue

                    self.stats['suspect_losses'].append({
                        'doc_id':      doc['id'],
                        'doc_name':    doc_name,
                        'moment':      doc.get('moment', '')[:10],
                        'store':       store_name,
                        'description': desc[:120],
                        'flags':       flags,
                        'is_slot_store': store_id in SLOT_STORES,
                        'positions': [
                            {
                                'name':     p.get('assortment', {}).get('name', '?'),
                                'qty':      p.get('quantity', 0),
                                'price':    p.get('price', 0) / 100,
                                'has_slot': p.get('slot') is not None,
                            }
                            for p in positions
                        ],
                    })

                print(f"    [{total}/{total}] Готово." + " " * 40)

            except Exception as e:
                print(f"  ❌ Ошибка при проверке {store_name}: {e}")

        print()

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

        Окно нарочно короче, чем doc_months: цена в документе сравнивается с FIFO
        «на сегодня», и для старых документов FIFO успевает законно измениться
        (распродажа старых партий) — получаются ложные тревоги задним числом.
        У свежего документа FIFO на дату создания ≈ FIFO сейчас, сравнение честное.

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

                for pos in positions:
                    price = pos.get("price", 0) or 0
                    assortment = pos.get("assortment", {})
                    product_name = assortment.get("name", "?")
                    href = assortment.get("meta", {}).get("href", "")
                    pid = href.split("/")[-1].split("?")[0] if href else None

                    if price == 0:
                        zero_positions.append(product_name)
                        continue

                    if pid and pid in stock_price_by_id:
                        avg = stock_price_by_id[pid]
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

    def check_suspect_moves(self):
        """Найти перемещения с нарушениями за последние N месяцев.

        Флаги:
          no_source_slot   — sourceStore адресный (SLOT_STORES) И позиция без sourceSlot
          reverse_direction — оба склада в DEFAULT_STORES, но направление не в NORMAL_MOVE_DIRECTIONS
          no_desc_large    — нет описания И сумма позиций > move_threshold руб
        """
        import time

        self._section_header(f"Перемещения (последние {self.doc_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            time.sleep(0.3)
            docs = self.h._get_all_pages("/entity/move", {
                "filter": f"moment>={date_from}",
                "order": "moment,desc",
                "expand": "sourceStore,targetStore",
            })
            applicable = [d for d in docs if d.get('applicable', False)]
            total = len(applicable)
            print(f"  Проведённых за период: {total}")

            for i, doc in enumerate(applicable, 1):
                source_id   = doc.get('sourceStore', {}).get('id', '')
                target_id   = doc.get('targetStore', {}).get('id', '')
                source_name = doc.get('sourceStore', {}).get('name', '?')
                target_name = doc.get('targetStore', {}).get('name', '?')
                doc_name    = doc.get('name', '?')
                desc        = (doc.get('description') or '')
                print(f"    [{i:2d}/{total}] №{doc_name} {source_name[:15]} → {target_name[:15]} ...", end='\r', flush=True)

                if doc['id'] in self.move_ack_ids or '[ok]' in desc.lower():
                    continue

                time.sleep(0.2)
                pos_result = self.h._get(f"/entity/move/{doc['id']}/positions", {
                    "limit": 100,
                    "expand": "sourceSlot,assortment",
                })
                positions = pos_result.get('rows', [])

                flags = []

                # no_source_slot: адресный склад → позиция без ячейки
                if source_id in SLOT_STORES:
                    if any(p.get('sourceSlot') is None for p in positions):
                        flags.append('no_source_slot')

                # reverse_direction: оба внутренних, но нетипичное направление
                if (source_id in DEFAULT_STORES and target_id in DEFAULT_STORES
                        and (source_id, target_id) not in NORMAL_MOVE_DIRECTIONS):
                    flags.append('reverse_direction')

                # no_desc_large: нет описания и крупная сумма
                if not desc:
                    total_value = sum(
                        p.get('price', 0) * p.get('quantity', 0) / 100
                        for p in positions
                    )
                    if total_value > self.move_threshold:
                        flags.append('no_desc_large')

                if not flags:
                    continue

                self.stats['suspect_moves'].append({
                    'doc_id':       doc['id'],
                    'doc_name':     doc_name,
                    'moment':       doc.get('moment', '')[:10],
                    'source_store': source_name,
                    'target_store': target_name,
                    'description':  desc[:120],
                    'flags':        flags,
                    'positions': [
                        {
                            'name':     p.get('assortment', {}).get('name', '?'),
                            'qty':      p.get('quantity', 0),
                            'price':    p.get('price', 0) / 100,
                            'has_slot': p.get('sourceSlot') is not None,
                        }
                        for p in positions
                    ],
                })

            print(f"    [{total}/{total}] Готово." + " " * 50)

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

        print()

    def check_suspect_supplies(self):
        """Найти приёмки с нарушениями за последние N месяцев.

        Флаги:
          zero_price       — цена 0 в позиции (критично: искажает себестоимость)
          no_slot          — приёмка на адресный склад (Шатл) и позиция без ячейки
          no_desc          — нет описания
          unexpected_store     — товар ранее поступал на Шатл, а текущая приёмка идёт
                               на склад производства (возможно ошибочный склад).
                               Если товар всегда шёл на производство — флаг не ставится.
          delivery_as_position — позиция с названием "доставка/перевозка/транспорт".
                               Должно быть в поле "Накладные расходы", не в позициях.
        """
        import time

        PRODUCTION_STORE_ID = "eaad5ec1-a4e0-11f0-0a80-1034002f3c11"
        SHATL_STORE_ID      = "41d3eec0-266b-11eb-0a80-090200155c69"

        self._section_header(f"Приёмки от поставщиков (последние {self.doc_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            time.sleep(0.3)
            docs = self.h._get_all_pages("/entity/supply", {
                "filter": f"moment>={date_from}",
                "order": "moment,asc",   # хронологический порядок — для накопления истории
                "expand": "store",
            })
            applicable = [d for d in docs if d.get('applicable', False)]
            total = len(applicable)
            print(f"  Проведённых за период: {total}")

            # product_shatl_count[product_id] = сколько раз товар принят на Шатл
            # до текущей приёмки (обновляется после каждой итерации)
            product_shatl_count = defaultdict(int)

            for i, doc in enumerate(applicable, 1):
                store_id   = doc.get('store', {}).get('id', '')
                store_name = doc.get('store', {}).get('name', '?')
                doc_name   = doc.get('name', '?')
                desc       = (doc.get('description') or '')
                print(f"    [{i:2d}/{total}] №{doc_name} → {store_name[:20]} ...", end='\r', flush=True)

                time.sleep(0.2)
                pos_result = self.h._get(f"/entity/supply/{doc['id']}/positions", {
                    "limit": 100,
                    "expand": "assortment,slot",
                })
                positions = pos_result.get('rows', [])

                if doc['id'] in self.supply_ack_ids or '[ok]' in desc.lower():
                    # Acknowledged — пропускаем флаги, но историю Шатла обновляем
                    if store_id == SHATL_STORE_ID:
                        for p in positions:
                            pid = p.get('assortment', {}).get('id', '')
                            if pid:
                                product_shatl_count[pid] += 1
                    continue

                flags = []

                # zero_price: цена 0 в любой позиции
                if any(p.get('price', 1) == 0 for p in positions):
                    flags.append('zero_price')

                # no_slot: только для адресных складов (Шатл)
                if store_id in SLOT_STORES:
                    if any(p.get('slot') is None for p in positions):
                        flags.append('no_slot')

                # no_desc: нет описания
                if not desc:
                    flags.append('no_desc')

                # delivery_as_position: доставка добавлена позицией вместо накладных расходов
                DELIVERY_KEYWORDS = ('доставк', 'delivery', 'перевозк', 'транспорт')
                if any(
                    any(kw in p.get('assortment', {}).get('name', '').lower() for kw in DELIVERY_KEYWORDS)
                    for p in positions
                ):
                    flags.append('delivery_as_position')

                # unexpected_store: приёмка на склад производства, но хотя бы один
                # товар в этой приёмке ранее поступал на Шатл → подозрительно
                if store_id == PRODUCTION_STORE_ID:
                    for p in positions:
                        pid = p.get('assortment', {}).get('id', '')
                        if pid and product_shatl_count[pid] > 0:
                            flags.append('unexpected_store')
                            break

                if flags:
                    total_value = sum(
                        p.get('price', 0) * p.get('quantity', 0) / 100
                        for p in positions
                    )
                    self.stats['suspect_supplies'].append({
                        'doc_id':        doc['id'],
                        'doc_name':      doc_name,
                        'moment':        doc.get('moment', '')[:10],
                        'store':         store_name,
                        'description':   desc[:120],
                        'flags':         flags,
                        'total_value':   total_value,
                        'is_slot_store': store_id in SLOT_STORES,
                        'positions': [
                            {
                                'name':     p.get('assortment', {}).get('name', '?'),
                                'qty':      p.get('quantity', 0),
                                'price':    p.get('price', 0) / 100,
                                'has_slot': p.get('slot') is not None,
                            }
                            for p in positions
                        ],
                    })

                # Обновить историю Шатла ПОСЛЕ оценки флагов текущей приёмки
                if store_id == SHATL_STORE_ID:
                    for p in positions:
                        pid = p.get('assortment', {}).get('id', '')
                        if pid:
                            product_shatl_count[pid] += 1

            print(f"    [{total}/{total}] Готово." + " " * 50)

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

        print()

    def check_suspect_sales_returns(self):
        """Найти проведённые возвраты от покупателей с нулевой себестоимостью позиций.

        Флаги:
          zero_cost_price — хотя бы одна позиция с cost=0 (поле называется
                            "cost", не "costPrice" — специфика salesreturn API).
                            При проведении МойСклад возвращает товар на склад
                            по этой цене, что занижает FIFO-себестоимость готовой продукции.

        Причина: большинство возвратов создаётся без привязки к исходной
        отгрузке (поле demand не заполнено), поэтому МойСклад не может
        автоматически определить себестоимость и ставит 0.

        Убрать из отчёта: [ok] в описании возврата или ID в salesreturns_acknowledged.json.
        """
        import time

        self._section_header(f"Возвраты от покупателей (последние {self.doc_months} мес.)")

        date_from = (datetime.now() - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            time.sleep(0.3)
            docs = self.h._get_all_pages("/entity/salesreturn", {
                "filter": f"moment>={date_from}",
                "order": "moment,desc",
                "expand": "agent",
            })
            applicable = [d for d in docs if d.get('applicable', False)]
            total = len(applicable)
            print(f"  Проведённых за период: {total}")

            for i, doc in enumerate(applicable, 1):
                doc_name = doc.get('name', '?')
                desc     = (doc.get('description') or '')
                moment   = doc.get('moment', '')[:10]
                agent    = doc.get('agent', {}).get('name', '') if doc.get('agent') else ''
                print(f"    [{i:3d}/{total}] №{doc_name} ...", end='\r', flush=True)

                if doc['id'] in self.salesreturn_ack_ids or '[ok]' in desc.lower():
                    continue

                # Возвраты С основанием (есть поле demand) — МойСклад считает себестоимость
                # автоматически из отгрузки, поле cost в позициях отсутствует.
                # Проверять их через positions бессмысленно — будет ложное срабатывание.
                if 'demand' in doc:
                    continue

                time.sleep(0.2)
                pos_result = self.h._get(f"/entity/salesreturn/{doc['id']}/positions", {
                    "limit": 100,
                    "expand": "assortment",
                })
                positions = pos_result.get('rows', [])

                # Ищем позиции с нулевой себестоимостью.
                # Только для возвратов БЕЗ основания — у них cost задаётся вручную.
                zero_cost = [
                    {
                        'name': p.get('assortment', {}).get('name', '?'),
                        'qty':  p.get('quantity', 0),
                        'sale_price': (p.get('price') or 0) / 100,
                    }
                    for p in positions
                    if (p.get('cost') or 0) == 0
                ]

                if not zero_cost:
                    continue

                self.stats['suspect_sales_returns'].append({
                    'doc_id':      doc['id'],
                    'doc_name':    doc_name,
                    'moment':      moment,
                    'agent':       agent,
                    'description': desc[:120],
                    'flags':       ['zero_cost_price'],
                    'zero_positions': zero_cost,
                    'total_positions': len(positions),
                })

            print(f"    [{total}/{total}] Готово." + " " * 50)

        except Exception as e:
            print(f"  ❌ Ошибка: {e}")

        print()

    def check_stale_drafts(self):
        """Найти непроведённые документы (черновики), которые не трогали более N дней.

        Порог: supply, enter, loss, move, inventory — 7 дней.
        Возвраты от покупателей здесь не проверяются — их черновики создаёт
        монитор возвратов намеренно (см. check_pending_returns).

        Признак «старый»: поле updated (дата последнего изменения) старше порога.
        Используем updated, а не moment, чтобы не ловить намеренно задним числом.
        """
        THRESHOLDS = [
            ('supply',      'Приёмки',                 7),
            ('enter',       'Оприходования',            7),
            ('loss',        'Списания',                 7),
            ('move',        'Перемещения',              7),
            ('inventory',   'Инвентаризации',           7),
        ]

        self._section_header("Незавершённые черновики (непроведённые документы)")

        now = datetime.now()
        date_from = (now - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')
        found_any = False

        for doc_type, label, days in THRESHOLDS:
            try:
                docs = self.h._get_all_pages(f"/entity/{doc_type}", {
                    "filter": f"moment>={date_from}",
                    "order": "updated,asc",
                })
                not_applicable = [d for d in docs if not d.get('applicable', True)]

                stale = []
                for doc in not_applicable:
                    updated_str = (doc.get('updated') or '')[:19].replace('T', ' ')
                    if not updated_str:
                        continue
                    try:
                        updated_dt = datetime.strptime(updated_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        continue
                    age_days = (now - updated_dt).days
                    if age_days >= days:
                        stale.append({
                            'doc_name':    doc.get('name', '?'),
                            'moment':      doc.get('moment', '')[:10],
                            'updated':     updated_str[:10],
                            'age_days':    age_days,
                            'description': (doc.get('description') or '')[:80],
                        })
                        self.stats['stale_drafts'].append({
                            'type':     label,
                            'ms_type':  doc_type,
                            'doc_id':   doc.get('id', ''),
                            'doc_name': doc.get('name', '?'),
                            'age_days': age_days,
                        })

                if stale:
                    found_any = True
                    print(f"  ⚠️  {label} ({len(stale)}) — не проведены >{days} дн.:")
                    for d in stale:
                        desc_str = f"  {d['description']}" if d['description'] else ''
                        print(f"    • №{d['doc_name']:<20}  дата {d['moment']}  "
                              f"изменён {d['updated']} ({d['age_days']} дн.){desc_str}")
                    print()

            except Exception as e:
                print(f"  ❌ Ошибка при проверке {label}: {e}")

        if not found_any:
            print("  ✅ Незавершённых черновиков не найдено\n")

        print()

    def check_pending_returns(self):
        """Возвраты от покупателей, ждущие поступления товара.

        Монитор возвратов (01_monitor_returns.py) создаёт возврат черновиком, когда
        интеграция маркетплейса ставит заказу статус «возврат». Черновик — штатное
        состояние: документ проводят, когда товар физически вернулся на склад.
        Проверка собирает все непроведённые возвраты за doc_months и считает
        зависшие деньги; возраст от даты документа (moment) — с этого момента
        начался процесс возврата. Старше PENDING_RETURN_WARN_DAYS — пора выяснять
        в кабинете маркетплейса, где товар.
        """
        self._section_header("Возвраты: ждут поступления товара")

        now = datetime.now()
        date_from = (now - timedelta(days=self.doc_months * 30)).strftime('%Y-%m-%d %H:%M:%S')

        try:
            docs = self.h._get_all_pages("/entity/salesreturn", {
                "filter": f"moment>={date_from}",
                "order": "moment,asc",
                "expand": "agent",
            })
        except Exception as e:
            print(f"  ❌ Ошибка при загрузке возвратов: {e}\n")
            return

        for doc in docs:
            if doc.get('applicable', True):
                continue
            moment = (doc.get('moment') or '')[:10]
            try:
                age_days = (now - datetime.strptime(moment, '%Y-%m-%d')).days
            except ValueError:
                age_days = 0
            self.stats['pending_returns'].append({
                'doc_id':      doc.get('id', ''),
                'doc_name':    doc.get('name', '?'),
                'moment':      moment,
                'age_days':    age_days,
                'sum_rub':     round(doc.get('sum', 0) / 100, 2),
                'agent':       (doc.get('agent') or {}).get('name', ''),
                'description': (doc.get('description') or '')[:120],
                'overdue':     age_days >= self.PENDING_RETURN_WARN_DAYS,
            })

        pending = self.stats['pending_returns']
        if pending:
            total = sum(p['sum_rub'] for p in pending)
            overdue = [p for p in pending if p['overdue']]
            print(f"  📦 Ждут поступления: {len(pending)} возвратов на {total:,.0f}р")
            if overdue:
                print(f"  ⚠️  Из них дольше {self.PENDING_RETURN_WARN_DAYS} дн.: "
                      f"{len(overdue)} на {sum(p['sum_rub'] for p in overdue):,.0f}р")
            for p in pending:
                marker = '⚠️ ' if p['overdue'] else '  '
                print(f"    {marker}№{p['doc_name']:<10} {p['moment']}  {p['age_days']:>3} дн."
                      f"  {p['sum_rub']:>10,.0f}р  {p['agent']}")
        else:
            print("  ✅ Непроведённых возвратов нет")

        print()
