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

    def report_negative_stock(self):
        if self.stats['negative_stock']:
            print(f"\n🔴 ОТРИЦАТЕЛЬНЫЕ ОСТАТКИ ({len(self.stats['negative_stock'])}):")
            print("-" * 70)
            for item in self.stats['negative_stock']:
                print(f"  {item['name'][:45]:<45}  {item['store'][:25]:<25}  {item['qty']:>8.3f}")
        else:
            print("\n✅ Отрицательных остатков не найдено")

    def report_enters(self):
        all_enters = self.stats['suspect_enters']
        if all_enters:
            manual = [e for e in all_enters if not e['is_auto']]
            auto   = [e for e in all_enters if e['is_auto']]

            print(f"\n📋 ОПРИХОДОВАНИЯ НА ВНУТРЕННИХ СКЛАДАХ за {self.enter_months} мес."
                  f"  (всего: {len(all_enters)}, ручных: {len(manual)}, авто: {len(auto)}):")
            print(f"   ↳ Ручные: проверь нет ли тех, что должны быть перемещениями")
            print("-" * 70)

            def _get_verdict(desc):
                """Авто-вердикт по описанию оприходования."""
                if not desc:
                    return "❓ Нет описания — стоит уточнить причину"
                d = desc.lower()
                if any(w in d for w in ['инвентар']):
                    return "✅ Инвентаризация — ожидаемо"
                if any(w in d for w in ['физическ', 'пересчит', 'взвесил', 'по факту', 'фактическ']):
                    return "✅ Физический пересчёт — ожидаемо"
                if any(w in d for w in ['ячейк', 'коррект', 'миграц']):
                    return "🔄 Корректировка ячеек/данных — ОК если товар уже был на складе"
                if any(w in d for w in ['минус', 'нулев', ' ноль', 'до нул', 'обнул']):
                    return "🔄 Обнуление отрицательных остатков"
                if any(w in d for w in ['задани', 'производств']):
                    return "🔄 Связь с производственным заданием"
                if any(w in d for w in ['авто:', 'auto:']):
                    return "✅ Авто-скрипт — создан программно"
                if any(w in d for w in ['перенос', 'перенести', 'переносил']):
                    return "⚠️ Упоминается перенос — возможно нужно перемещение вместо оприходования"
                if any(w in d for w in ['не хватает', 'недостача', 'нехватка']):
                    return "⚠️ Нехватка — проверь откуда взялся товар"
                return "ℹ️ Проверь: это точно оприходование, а не перемещение?"

            def _print_enter(item, marker):
                desc = item['description'] or ''
                desc_display = desc[:100] if desc else '(без описания)'
                positions = item['positions']
                pos_count = len(positions)
                verdict = _get_verdict(desc)

                print(f"  {marker} №{item['doc_name']:<26}  {item['moment']}  {item['store']}")
                print(f"      📝 {desc_display}")

                if positions:
                    p0 = positions[0]
                    price_str = f"{p0['price']:.2f} руб" if p0['price'] > 0 else "⚠️ цена 0!"
                    more = f" + ещё {pos_count - 1} поз." if pos_count > 1 else ""
                    slot_warn = "  ⚠️ нет ячейки (Шатл — адресный склад)" if item.get('no_slot') else ""
                    print(f"      📦 {p0['name'][:42]:<42}  x{p0['qty']:.0f}  {price_str}{more}{slot_warn}")

                print(f"      💡 {verdict}")
                print()

            if manual:
                print(f"  ⚠️  РУЧНЫЕ ({len(manual)}) — требуют проверки:")
                for item in manual:
                    _print_enter(item, '⚠️')
            if auto:
                print(f"  ℹ️  АВТО ({len(auto)}) — созданы скриптами:")
                for item in auto:
                    _print_enter(item, 'ℹ️')
        else:
            print(f"\n✅ Оприходований на внутренних складах не найдено"
                  f" (последние {self.enter_months} мес.)")

    def report_losses(self):
        losses = self.stats['suspect_losses']
        if losses:
            print(f"\n🗑️  СПИСАНИЯ С НАРУШЕНИЯМИ ({len(losses)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ Проверь: нет ли потерь без причины или с нулевой ценой")
            print("-" * 70)
            for item in losses:
                flag_labels = []
                if 'no_desc' in item['flags']:
                    flag_labels.append('нет описания')
                if 'zero_price' in item['flags']:
                    flag_labels.append('нулевая цена')
                if 'no_slot' in item['flags']:
                    flag_labels.append('нет ячейки (Шатл — адресный склад)')
                desc_display = item['description'] or '(без описания)'
                print(f"  🔴 №{item['doc_name']:<26}  {item['moment']}  {item['store']}")
                print(f"      📝 {desc_display[:100]}")
                if item['positions']:
                    no_slot_pos = [p for p in item['positions'] if not p.get('has_slot')] if item.get('is_slot_store') else []
                    show = (no_slot_pos or item['positions'])[:1]
                    for p0 in show:
                        price_str = f"{p0['price']:.2f} руб" if p0['price'] > 0 else "⚠️ цена 0!"
                        more = f" + ещё {len(item['positions']) - 1} поз." if len(item['positions']) > 1 else ""
                        slot_warn = "  ⚠️ нет ячейки" if (item.get('is_slot_store') and not p0.get('has_slot')) else ""
                        print(f"      📦 {p0['name'][:42]:<42}  x{p0['qty']:.0f}  {price_str}{more}{slot_warn}")
                print(f"      ⚠️ {', '.join(flag_labels)}")
                print()
        else:
            print(f"\n✅ Списаний с нарушениями не найдено (последние {self.doc_months} мес.)")

    def summary_negative_stock(self):
        print(f"  🔴 Отрицательных остатков: {len(self.stats['negative_stock'])}")

    def summary_enters(self):
        manual_cnt = sum(1 for e in self.stats['suspect_enters'] if not e['is_auto'])
        auto_cnt   = sum(1 for e in self.stats['suspect_enters'] if e['is_auto'])
        print(f"  📋 Оприходований на внутренних складах: {len(self.stats['suspect_enters'])}"
              f"  (ручных: {manual_cnt}, авто: {auto_cnt})")

    def summary_losses(self):
        print(f"  🗑️  Списаний с нарушениями: {len(self.stats['suspect_losses'])}")

    def export_negative_stock(self, add):
        add('negative_stock', 'Отрицательные остатки', None, None, [
            {
                'key': '', 'ms_id': '', 'object': it['name'], 'severity': 'important',
                'detail': f"{it['store']} · {it['qty']:.3f}",
            }
            for it in self.stats['negative_stock']
        ])

    def export_enters(self, add):
        def _enter_detail(it):
            parts = [it['moment'], it['store']]
            if it.get('no_slot'):
                parts.append('нет ячейки')
            if it.get('description'):
                parts.append(it['description'][:60])
            return ' · '.join(parts)
        add('suspect_enters', 'Оприходования на внутренних складах', 'enters', 'enter', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}",
                'severity': 'warning' if it.get('is_auto') else 'important',
                'detail': _enter_detail(it),
            }
            for it in self.stats['suspect_enters']
        ])

    def export_losses(self, add):
        _loss_flag = {'no_desc': 'нет описания', 'zero_price': 'нулевая цена', 'no_slot': 'нет ячейки'}
        add('suspect_losses', 'Списания с нарушениями', 'losses', 'loss', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}", 'severity': 'important',
                'detail': f"{it['moment']} · {it['store']} · "
                          f"{', '.join(_loss_flag.get(f, f) for f in it['flags'])}",
            }
            for it in self.stats['suspect_losses']
        ])
