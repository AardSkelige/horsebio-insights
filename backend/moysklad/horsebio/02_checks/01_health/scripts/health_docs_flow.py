from collections import defaultdict
from datetime import datetime, timedelta

from health_config import DEFAULT_STORES, SLOT_STORES, NORMAL_MOVE_DIRECTIONS


class FlowDocChecksMixin:
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

    def check_stale_drafts(self):
        """Найти непроведённые документы (черновики), которые не трогали более N дней.

        Порог: supply, enter, loss, move, inventory — 7 дней.
        Возвраты от покупателей здесь не проверяются — их черновики создаёт
        монитор возвратов намеренно (см. проверку «Возвраты в пути»).

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

    def report_moves(self):
        moves = self.stats['suspect_moves']
        if moves:
            print(f"\n🚚 ПЕРЕМЕЩЕНИЯ С НАРУШЕНИЯМИ ({len(moves)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ Проверь: ячейки при отгрузке с Шатла, направление, крупные без описания")
            print("-" * 70)
            for item in moves:
                flag_labels = []
                if 'no_source_slot' in item['flags']:
                    flag_labels.append('нет ячейки (адресный склад)')
                if 'reverse_direction' in item['flags']:
                    flag_labels.append('нетипичное направление')
                if 'no_desc_large' in item['flags']:
                    flag_labels.append(f'крупное без описания (>{self.move_threshold} руб)')
                desc_display = item['description'] or '(без описания)'
                print(f"  🔴 №{item['doc_name']:<26}  {item['moment']}  "
                      f"{item['source_store']} → {item['target_store']}")
                print(f"      📝 {desc_display[:100]}")
                # Сначала позиции без ячейки, потом остальные
                no_slot = [p for p in item['positions'] if not p['has_slot']]
                with_slot = [p for p in item['positions'] if p['has_slot']]
                show_positions = (no_slot or with_slot)[:1]
                for p in show_positions:
                    slot_warn = "" if p['has_slot'] else "  ⚠️ нет ячейки"
                    extra = ""
                    total_no_slot = len(no_slot)
                    if not p['has_slot'] and total_no_slot > 1:
                        extra = f" + ещё {total_no_slot - 1} без ячейки"
                    print(f"      📦 {p['name'][:42]:<42}  x{p['qty']:.0f}{slot_warn}{extra}")
                print(f"      ⚠️ {', '.join(flag_labels)}")
                print()
        else:
            print(f"\n✅ Перемещений с нарушениями не найдено (последние {self.doc_months} мес.)")

    def report_supplies(self):
        supplies = self.stats['suspect_supplies']
        if supplies:
            print(f"\n🚚 ПРИЁМКИ С НАРУШЕНИЯМИ ({len(supplies)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ Проверь: цены, ячейки на Шатле, описание, правильный склад")
            print("-" * 70)
            for item in supplies:
                flag_labels = []
                if 'zero_price' in item['flags']:
                    flag_labels.append('⛔ цена 0 — искажает себестоимость!')
                if 'no_slot' in item['flags']:
                    flag_labels.append('нет ячейки (Шатл — адресный склад)')
                if 'no_desc' in item['flags']:
                    flag_labels.append('нет описания')
                if 'unexpected_store' in item['flags']:
                    flag_labels.append('⚠️ склад производства — товар ранее шёл через Шатл')
                if 'delivery_as_position' in item['flags']:
                    flag_labels.append('⚠️ доставка позицией — нужно в Накладные расходы')
                marker = "🚨" if 'zero_price' in item['flags'] or 'unexpected_store' in item['flags'] or 'delivery_as_position' in item['flags'] else "🔴"
                desc_display = item['description'] or '(без описания)'
                value_str = f"{item['total_value']:,.0f} руб" if item['total_value'] else ''
                print(f"  {marker} №{item['doc_name']:<26}  {item['moment']}  {item['store']}  {value_str}")
                print(f"      📝 {desc_display[:100]}")
                zero_pos = [p for p in item['positions'] if p['price'] == 0]
                # нет ячейки — только для адресных складов (Шатл)
                no_slot_pos = [p for p in item['positions'] if not p['has_slot']] if item.get('is_slot_store') else []
                show = (zero_pos or no_slot_pos or item['positions'])[:1]
                for p in show:
                    price_str = f"{p['price']:.2f} руб" if p['price'] > 0 else "⚠️ цена 0!"
                    slot_warn = "" if (p['has_slot'] or not item.get('is_slot_store')) else "  ⚠️ нет ячейки"
                    extra_no_slot = f" + ещё {len(no_slot_pos)-1} без ячейки" if len(no_slot_pos) > 1 and not p['has_slot'] else ""
                    extra_zero = f" + ещё {len(zero_pos)-1} с ценой 0" if len(zero_pos) > 1 and p['price'] == 0 else ""
                    total_pos = len(item['positions'])
                    more = f" (всего {total_pos} поз.)" if total_pos > 1 else ""
                    print(f"      📦 {p['name'][:42]:<42}  x{p['qty']:.0f}  {price_str}{slot_warn}{extra_no_slot}{extra_zero}{more}")
                print(f"      ⚠️ {', '.join(flag_labels)}")
                print()
        else:
            print(f"\n✅ Приёмок с нарушениями не найдено (последние {self.doc_months} мес.)")

    def summary_moves(self):
        print(f"  🚚 Перемещений с нарушениями: {len(self.stats['suspect_moves'])}")

    def summary_supplies(self):
        print(f"  🚚 Приёмок с нарушениями: {len(self.stats['suspect_supplies'])}")

    def summary_stale_drafts(self):
        stale_cnt = len(self.stats['stale_drafts'])
        if stale_cnt:
            print(f"  🕐 Незавершённых черновиков: {stale_cnt} — не проведены дольше порога")
        else:
            print(f"  ✅ Незавершённых черновиков не найдено")

    def export_moves(self, add):
        _move_flag = {'no_source_slot': 'нет ячейки', 'reverse_direction': 'нетипичное направление',
                      'no_desc_large': 'крупное без описания'}
        add('suspect_moves', 'Перемещения с нарушениями', 'moves', 'move', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}", 'severity': 'important',
                'detail': f"{it['moment']} · {it['source_store']} → {it['target_store']} · "
                          f"{', '.join(_move_flag.get(f, f) for f in it['flags'])}",
            }
            for it in self.stats['suspect_moves']
        ])

    def export_supplies(self, add):
        _supply_flag = {'zero_price': '⛔ цена 0', 'no_slot': 'нет ячейки', 'no_desc': 'нет описания',
                        'unexpected_store': 'неожиданный склад', 'delivery_as_position': 'доставка позицией'}
        _supply_crit = {'zero_price', 'unexpected_store', 'delivery_as_position'}
        add('suspect_supplies', 'Приёмки с нарушениями', 'supplies', 'supply', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}",
                'severity': 'critical' if _supply_crit & set(it['flags']) else 'important',
                'detail': f"{it['moment']} · {it['store']} · "
                          f"{', '.join(_supply_flag.get(f, f) for f in it['flags'])}",
            }
            for it in self.stats['suspect_supplies']
        ])

    def export_stale_drafts(self, add):
        # Ссылка собирается на каждый документ: типы разные, а документы открываются по API-id
        add('stale_drafts', 'Незавершённые черновики', None, None, [
            {'key': '', 'ms_id': it.get('doc_id', ''),
             'ms_href': (f"https://online.moysklad.ru/app/#{it['ms_type']}/edit?id={it['doc_id']}"
                         if it.get('ms_type') and it.get('doc_id') else ''),
             'object': it.get('doc_name', '?'), 'severity': 'warning',
             'detail': f"{it.get('type', '')} · {it.get('age_days', 0)} дн"}
            for it in self.stats['stale_drafts']
        ])
