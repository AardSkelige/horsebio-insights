"""Отчётность health-чеков: консольный отчёт и JSON-экспорт для страницы /checks."""
import json
from datetime import datetime


class ReportingMixin:
    """Формирование отчётов CostHealthCheck (используется как примесь)."""

    def print_report(self):
        """Вывести отчёт"""

        print("\n" + "="*70)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("="*70 + "\n")

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
            _unknown   = [i for i in self.stats['important']
                          if _notes_map.get(i.get('product_code', ''), {}).get('status') != 'норма']
            _explained = [i for i in self.stats['important']
                          if _notes_map.get(i.get('product_code', ''), {}).get('status') == 'норма']

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

        # Объяснённые отклонения (avg_deviations_ignore.json)
        # Показываем всегда если есть — чтобы видеть актуальное отклонение.
        # Оприходования с неправильной ценой
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

        # Отрицательные остатки
        if self.stats['negative_stock']:
            print(f"\n🔴 ОТРИЦАТЕЛЬНЫЕ ОСТАТКИ ({len(self.stats['negative_stock'])}):")
            print("-" * 70)
            for item in self.stats['negative_stock']:
                print(f"  {item['name'][:45]:<45}  {item['store'][:25]:<25}  {item['qty']:>8.3f}")
        else:
            print("\n✅ Отрицательных остатков не найдено")

        # Оприходования на внутренних складах
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

        # Списания
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

        # Инвентаризации
        # Цены в инвентаризациях
        inv_price_issues = self.stats['inventory_price_issues']
        if inv_price_issues:
            print(f"\n💰 ИНВЕНТАРИЗАЦИИ С ПРОБЛЕМАМИ ЦЕН ({len(inv_price_issues)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ zero_price: демон не отработал или товар без остатка. big_deviation: цена отличается от FIFO-себестоимости >30%")
            print("-" * 70)
            for item in inv_price_issues:
                status = "непроведена" if not item['applicable'] else "проведена"
                print(f"  🔴 №{item['doc_name']:<26}  {item['moment']}  {item['store']}  [{status}]")
                if item['zero_positions']:
                    names = ', '.join(p[:30] for p in item['zero_positions'])
                    more = f" + ещё {len(item['zero_positions']) - len(item['zero_positions'][:5])}" if len(item['zero_positions']) > 5 else ""
                    print(f"      ⛔ Нулевая цена: {names}{more}")
                for p in item['deviation_positions']:
                    print(f"      ⚠️  {p['name'][:40]:<40}  {p['price_rub']:.2f} руб (FIFO: {p['avg_rub']:.2f}, откл. {p['deviation_pct']}%)")
                print()
        else:
            print(f"\n✅ Цен с проблемами в инвентаризациях не найдено (последние {self.doc_months} мес.)")

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

        # Перемещения
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

        # Приёмки
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

        # Возвраты от покупателей с нулевой себестоимостью
        sales_returns = self.stats['suspect_sales_returns']
        if sales_returns:
            print(f"\n↩️  ВОЗВРАТЫ С НУЛЕВОЙ СЕБЕСТОИМОСТЬЮ ({len(sales_returns)})  — последние {self.doc_months} мес.:")
            print(f"   ↳ costPrice=0 в позиции → товар вернулся на склад по цене 0 → занижает FIFO-себестоимость готовой продукции")
            print(f"   ↳ Исправить: задним числом поставить costPrice = текущей FIFO-себестоимости OR исправить через списание+оприходование")
            print("-" * 70)
            for item in sales_returns:
                agent_str = f"  {item['agent'][:30]}" if item['agent'] else ''
                desc_display = item['description'] or '(без описания)'
                zero_count = len(item['zero_positions'])
                total_pos = item['total_positions']
                print(f"  🔴 №{item['doc_name']:<26}  {item['moment']}{agent_str}")
                print(f"      📝 {desc_display[:100]}")
                for p in item['zero_positions'][:3]:
                    print(f"      📦 {p['name'][:50]:<50}  x{p['qty']:.0f}  цена_продажи={p['sale_price']:.2f}р  ⚠️ себест.=0.00р")
                if zero_count > 3:
                    print(f"      ... и ещё {zero_count - 3} поз. с нулевой себестоимостью")
                print(f"      ⚠️ нулевая себестоимость в {zero_count} из {total_pos} позиций")
                print()
        else:
            print(f"\n✅ Возвратов с нулевой себестоимостью не найдено (последние {self.doc_months} мес.)")

        # Скачки цен в приёмках
        if self.stats['supply_jumps']:
            print(f"\n📦 СКАЧКИ ЦЕН В ПРИЁМКАХ ({len(self.stats['supply_jumps'])}):")
            print("-" * 70)
            for item in sorted(self.stats['supply_jumps'], key=lambda x: x['jump_pct'], reverse=True):
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
                        f"{h['price']:>10.2f} руб  x{qty_str}"
                    )
                print()

        # Статистика
        print(f"\n{'='*70}")
        print("СТАТИСТИКА:")
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
        enter_issues_cnt = len(self.stats['enter_price_issues'])
        if enter_issues_cnt:
            zero_cnt = sum(1 for i in self.stats['enter_price_issues'] if i['enter_cost'] == 0)
            print(f"  🔧 Оприходования с неправильной ценой: {enter_issues_cnt} (нулевых: {zero_cnt})")
        else:
            print(f"  ✅ Свежих оприходований с неправильной ценой не найдено")
        print(f"  🔴 Отрицательных остатков: {len(self.stats['negative_stock'])}")
        manual_cnt = sum(1 for e in self.stats['suspect_enters'] if not e['is_auto'])
        auto_cnt   = sum(1 for e in self.stats['suspect_enters'] if e['is_auto'])
        print(f"  📋 Оприходований на внутренних складах: {len(self.stats['suspect_enters'])}"
              f"  (ручных: {manual_cnt}, авто: {auto_cnt})")
        print(f"  🗑️  Списаний с нарушениями: {len(self.stats['suspect_losses'])}")
        print(f"  📋 Инвентаризаций с расхождениями: {len(self.stats['suspect_inventories'])}")
        inv_price_issues = self.stats['inventory_price_issues']
        if inv_price_issues:
            zero_cnt = sum(1 for i in inv_price_issues if 'zero_price' in i['flags'])
            dev_cnt = sum(1 for i in inv_price_issues if 'big_deviation' in i['flags'])
            print(f"  💰 Инвентаризаций с проблемами цен: {len(inv_price_issues)} "
                  f"(нулевые: {zero_cnt}, отклонение >30%: {dev_cnt})")
        else:
            print(f"  ✅ Цены в инвентаризациях — всё в порядке")
        print(f"  🚚 Перемещений с нарушениями: {len(self.stats['suspect_moves'])}")
        print(f"  🚚 Приёмок с нарушениями: {len(self.stats['suspect_supplies'])}")
        sr_cnt = len(self.stats['suspect_sales_returns'])
        if sr_cnt:
            print(f"  ↩️  Возвратов с нулевой себест.: {sr_cnt}  ← занижают FIFO-себестоимость ГП!")
        else:
            print(f"  ✅ Возвратов с нулевой себестоимостью не найдено")
        new_jumps = len(self.stats['supply_jumps'])
        explained = len(self.stats['supply_jumps_explained'])
        if new_jumps:
            print(f"  📦 Скачков цен в приёмках: {new_jumps}  ← требуют проверки")
        elif explained:
            print(f"  ✅ Скачков цен в приёмках: 0  ({explained} в игнор-листе — известные позиции)")
        else:
            print(f"  ✅ Скачков цен в приёмках: 0")
        no_code_cnt = len(self.stats['code_no_code'])
        dup_cnt = len(self.stats['code_duplicates'])
        suspect_cnt = len(self.stats['code_suspect'])
        if no_code_cnt or dup_cnt or suspect_cnt:
            print(f"  🏷️  Коды товаров: без кода {no_code_cnt}, дублей {dup_cnt}, аномалий {suspect_cnt}")
        else:
            print(f"  ✅ Коды товаров — всё в порядке")
        ez_cnt = len(self.stats['enter_zero_prices'])
        if ez_cnt:
            total_pos = sum(len(i['positions']) for i in self.stats['enter_zero_prices'])
            print(f"  ❌ Оприходований с нулевой ценой: {ez_cnt} документа(ов), {total_pos} позиций — занижают FIFO-себестоимость!")
        else:
            print(f"  ✅ Нулевых цен в оприходованиях не найдено")
        stale_cnt = len(self.stats['stale_drafts'])
        if stale_cnt:
            print(f"  🕐 Незавершённых черновиков: {stale_cnt} — не проведены дольше порога")
        else:
            print(f"  ✅ Незавершённых черновиков не найдено")
        pending = self.stats['pending_returns']
        if pending:
            overdue = sum(1 for p in pending if p['overdue'])
            total = sum(p['sum_rub'] for p in pending)
            tail = f", из них {overdue} дольше {self.PENDING_RETURN_WARN_DAYS} дн." if overdue else ''
            print(f"  📦 Возвраты ждут товара: {len(pending)} на {total:,.0f}р{tail}")
        else:
            print(f"  ✅ Возвратов в ожидании нет")

        print("="*70 + "\n")

    # ─── Стандартизированный JSON результатов (для страницы /checks) ──────────
    _SEVERITY_RANK = {'critical': 3, 'important': 2, 'warning': 1, 'info': 0}

    def export_results(self, path):
        """Сериализовать self.stats в стандартизированный JSON находок.

        Формат используется страницей /checks: категории с severity и kind (тип
        исключения), у каждой находки — key (doc_id/product_code/name) для кнопки
        «в исключения» и ms_id для ссылки в МойСклад.
        """
        import json as _json
        from datetime import datetime as _dt

        categories = []

        def money(v):
            try:
                return f"{v:.2f}р"
            except Exception:
                return str(v)

        def add(key, title, kind, ms_type, items):
            if not items:
                return
            sev = max((it['severity'] for it in items),
                      key=lambda s: self._SEVERITY_RANK.get(s, 0))
            categories.append({
                'key': key, 'title': title, 'kind': kind, 'ms_type': ms_type,
                'severity': sev, 'count': len(items), 'items': items,
            })

        # 1-3. Отклонения FIFO vs приёмка.
        # Позиции, помеченные «норма» (исключение), не исчезают из отчёта по логике скрипта —
        # выносим их в отдельную тихую группу, чтобы «Критичные/Важные» показывали только то,
        # что реально требует внимания.
        _notes = self.deviations_notes_map

        def _is_normal(it):
            """«Норма» действует, пока отклонение не выросло заметно с момента разбора.

            deviation_pct в note — размер отклонения, когда его подтверждали.
            Вырасло в 1.5 раза (плюс 2 п.п. буфера от шума на малых процентах) —
            вердикт устарел, позиция снова попадает в проблемные."""
            note = _notes.get(it.get('product_code', ''), {})
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

        _phref = getattr(self, '_product_uuid_href', {})

        def _dev_item(it, sev):
            sign = '+' if it['current_cost'] > it['last_supply_cost'] else '−'
            msg = it.get('message')
            head = f"{msg} · " if (sev == 'critical' and msg) else f"{sign}{it['deviation_pct']:.1f}% · "
            return {
                'key': it.get('product_code') or '', 'ms_id': it.get('product_id') or '',
                'ms_href': _phref.get(it.get('product_id')) or '',
                'object': it['product_name'], 'severity': sev,
                # deviation_pct нужен UI: запоминается в исключении при разборе,
                # чтобы снова флагать позицию, когда отклонение вырастет
                'deviation_pct': round(it.get('deviation_pct', 0), 1),
                'detail': head + f"{it['store_name']} · FIFO {money(it['current_cost'])} ↔ "
                          f"приёмка {money(it['last_supply_cost'])} · запас {it.get('stock', 0):,.0f} ед",
            }

        # ms_type=None: ссылка на товар только через uuidHref (ms_href) — UI-id ≠ API-id,
        # fallback #good/edit?id=<api id> всегда ведёт на «Объект не найден»
        add('critical', 'Критичные: FIFO vs приёмка', 'deviations', None,
            [_dev_item(it, 'critical') for it in self.stats['critical'] if not _is_normal(it)])
        add('important', 'Важные: отклонения FIFO vs приёмка', 'deviations', None,
            [_dev_item(it, 'important') for it in self.stats['important'] if not _is_normal(it)])
        add('deviations_normal', 'Отклонения, разобранные как норма', 'deviations', None,
            [_dev_item(it, 'ok') for it in (self.stats['critical'] + self.stats['important']) if _is_normal(it)])

        # 3. Оприходования с неправильной ценой (без исключений — информативно)
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

        # 4. Отрицательные остатки (без исключений)
        add('negative_stock', 'Отрицательные остатки', None, None, [
            {
                'key': '', 'ms_id': '', 'object': it['name'], 'severity': 'important',
                'detail': f"{it['store']} · {it['qty']:.3f}",
            }
            for it in self.stats['negative_stock']
        ])

        # 5. Оприходования на внутренних складах
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

        # 6. Списания с нарушениями
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

        # 7. Инвентаризации с расхождениями
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

        # 8. Инвентаризации: проблемы цен (тот же ack-файл, что инвентаризации)
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

        # 9. Перемещения с нарушениями
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

        # 10. Приёмки с нарушениями
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

        # 11. Возвраты с нулевой себестоимостью
        add('suspect_sales_returns', 'Возвраты с нулевой себестоимостью', 'salesreturns', 'salesreturn', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}", 'severity': 'critical',
                'detail': f"{it['moment']}"
                          + (f" · {it['agent'][:30]}" if it.get('agent') else '')
                          + f" · нулевая себест. в {len(it['zero_positions'])} из {it['total_positions']} поз.",
            }
            for it in self.stats['suspect_sales_returns']
        ])

        # 12. Оприходования с нулевой ценой позиций
        add('enter_zero_prices', 'Оприходования с нулевой ценой', 'enter_zero', 'enter', [
            {
                'key': it['doc_id'], 'ms_id': it['doc_id'],
                'object': f"№{it['doc_name']}", 'severity': 'critical',
                'detail': f"{it.get('doc_date', '')} · {len(it['positions'])} поз. с ценой 0"
                          + (f" · {it['doc_desc']}" if it.get('doc_desc') else ''),
            }
            for it in self.stats['enter_zero_prices']
        ])

        # 13. Скачки цен в приёмках. last_doc нужен UI для разового исключения
        # (extra.supply_doc — глушит только скачок этой приёмки).
        add('supply_jumps', 'Скачки цен в приёмках', 'supply_jumps', None, [
            {
                'key': it['name'], 'ms_id': '',
                'object': it['name'], 'severity': 'warning',
                'last_doc': it.get('last_doc', ''),
                'detail': f"{'▲' if it['last_price'] > it['avg_prev'] else '▼'} {it['jump_pct']:.1f}% · "
                          f"последняя {money(it['last_price'])} ↔ средняя {money(it['avg_prev'])} · "
                          f"приёмка №{it.get('last_doc', '?')} {it.get('last_date', '')}",
            }
            for it in self.stats['supply_jumps']
        ])

        # 14-16. Коды товаров (без исключений)
        add('code_no_code', 'Товары без кода', None, None, [
            {'key': '', 'ms_id': '', 'object': it['name'], 'severity': 'warning',
             'detail': it.get('group', '')}
            for it in self.stats['code_no_code']
        ])
        add('code_duplicates', 'Дубли кодов', None, None, [
            {'key': '', 'ms_id': '', 'object': f"код {code}", 'severity': 'warning',
             'detail': ', '.join(p.get('name', '?') for p in products)}
            for code, products in self.stats['code_duplicates'].items()
        ])
        add('code_suspect', 'Аномальные коды', None, None, [
            {'key': '', 'ms_id': '', 'object': it['name'], 'severity': 'warning',
             'detail': f"код {it.get('code', '')} · {it.get('group', '')}"}
            for it in self.stats['code_suspect']
        ])

        # 17. Незавершённые черновики (без исключений). Типы документов в категории
        # разные, поэтому ссылка собирается per-item (документы, в отличие от товаров,
        # открываются в UI по API-id).
        add('stale_drafts', 'Незавершённые черновики', None, None, [
            {'key': '', 'ms_id': it.get('doc_id', ''),
             'ms_href': (f"https://online.moysklad.ru/app/#{it['ms_type']}/edit?id={it['doc_id']}"
                         if it.get('ms_type') and it.get('doc_id') else ''),
             'object': it.get('doc_name', '?'), 'severity': 'warning',
             'detail': f"{it.get('type', '')} · {it.get('age_days', 0)} дн"}
            for it in self.stats['stale_drafts']
        ])

        # 18. Возвраты, ждущие поступления товара. Не часть хелс-чека — отдельный
        # индикатор на странице /checks (черновик тут штатное состояние), поэтому
        # категория не участвует в сводке severity ниже.
        add('pending_returns', 'Возвраты: ждут поступления товара', None, None, [
            {
                'key': '', 'ms_id': it['doc_id'],
                'ms_href': (f"https://online.moysklad.ru/app/#salesreturn/edit?id={it['doc_id']}"
                            if it['doc_id'] else ''),
                'object': f"№{it['doc_name']}",
                'severity': 'warning' if it['overdue'] else 'info',
                'sum_rub': it['sum_rub'],
                'age_days': it['age_days'],
                'detail': f"{it['moment']} · {it['age_days']} дн · {money(it['sum_rub'])}"
                          + (f" · {it['agent']}" if it['agent'] else ''),
            }
            for it in self.stats['pending_returns']
        ])

        # Сетка статусов всех проверок, включая чистые (для деталки /checks).
        # Одна плитка = одна проверка; cats — ключи категорий с её находками.
        _CHECKS_GRID = [
            ('deviations',        'Отклонения FIFO vs приёмка',   ['critical', 'important']),
            ('negative_stock',    'Отрицательные остатки',        ['negative_stock']),
            ('enters',            'Оприходования: внутр. склады', ['suspect_enters']),
            ('enter_prices',      'Оприходования: цена ≠ приёмка', ['enter_price_issues']),
            ('enter_zero',        'Оприходования: нулевые цены',  ['enter_zero_prices']),
            ('losses',            'Списания',                     ['suspect_losses']),
            ('inventories',       'Инвентаризации',               ['suspect_inventories', 'inventory_price_issues']),
            ('moves',             'Перемещения',                  ['suspect_moves']),
            ('supplies',          'Приёмки',                      ['suspect_supplies']),
            ('salesreturns',      'Возвраты: нулевая себест.',    ['suspect_sales_returns']),
            ('supply_jumps',      'Скачки цен в приёмках',        ['supply_jumps']),
            ('codes',             'Коды товаров',                 ['code_no_code', 'code_duplicates', 'code_suspect']),
            ('stale_drafts',      'Незавершённые черновики',      ['stale_drafts']),
        ]
        cat_by_key = {c['key']: c for c in categories}
        checks_grid = []
        for check_id, title, cat_keys in _CHECKS_GRID:
            if check_id == 'supply_jumps' and not getattr(self, 'full_mode', False):
                checks_grid.append({'id': check_id, 'title': title, 'status': 'skipped',
                                    'count': 0, 'severity': None, 'cats': []})
                continue
            present = [cat_by_key[k] for k in cat_keys if k in cat_by_key]
            count = sum(c['count'] for c in present)
            sev = max((c['severity'] for c in present),
                      key=lambda s: self._SEVERITY_RANK.get(s, 0)) if present else None
            checks_grid.append({
                'id': check_id, 'title': title,
                'status': 'problems' if count else 'ok',
                'count': count, 'severity': sev,
                'cats': [c['key'] for c in present],
            })

        # Сводка (pending_returns — индикатор, не находки чека)
        sev_counts = {'critical': 0, 'important': 0, 'warning': 0}
        cat_counts = {}
        for cat in categories:
            cat_counts[cat['key']] = cat['count']
            if cat['key'] == 'pending_returns':
                continue
            for it in cat['items']:
                s = it['severity']
                if s in sev_counts:
                    sev_counts[s] += 1

        payload = {
            'generated_at': _dt.now().isoformat(timespec='seconds'),
            'params': {
                'threshold': self.threshold,
                'supply_threshold': self.supply_threshold,
                'enter_months': self.enter_months,
                'doc_months': self.doc_months,
            },
            'summary': {
                'critical': sev_counts['critical'],
                'important': sev_counts['important'],
                'warnings': sev_counts['warning'],
                'ok': self.stats.get('ok', 0),
                'categories': cat_counts,
                'pending_returns': {
                    'count': len(self.stats['pending_returns']),
                    'total_rub': round(sum(p['sum_rub'] for p in self.stats['pending_returns']), 2),
                    'overdue': sum(1 for p in self.stats['pending_returns'] if p['overdue']),
                    'overdue_rub': round(sum(p['sum_rub'] for p in self.stats['pending_returns'] if p['overdue']), 2),
                    'warn_days': self.PENDING_RETURN_WARN_DAYS,
                },
                # Внутри summary, потому что ingest сохраняет в БД только summary и categories
                'checks': checks_grid,
            },
            'categories': categories,
        }

        with open(path, 'w', encoding='utf-8') as f:
            _json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Результаты сохранены: {path}")
