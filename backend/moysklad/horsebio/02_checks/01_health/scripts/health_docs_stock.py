from datetime import datetime, timedelta

from health_config import DEFAULT_STORES, SLOT_STORES


class StockDocChecksMixin:
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
