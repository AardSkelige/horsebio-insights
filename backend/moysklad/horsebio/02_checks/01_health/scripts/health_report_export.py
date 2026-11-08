from health_production import rows_detail


class ExportReportMixin:
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
                          and not _is_normal(it)),
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

        add('stuck_production', 'Зависшие производственные задания', None, None, [
            {'key': '', 'ms_id': it['doc_id'], 'ms_href': it['href'],
             'object': f"№{it['doc_name']}", 'severity': 'warning',
             'detail': f"{it['date_label']} {it['planned']} ({it['age_days']} дн) · висит {' и '.join(it['flags'])} · "
                       + rows_detail(it['rows'])}
            for it in self.stats['stuck_production']
        ] + [
            {'key': '', 'ms_id': it['doc_id'], 'ms_href': it['href'],
             'object': f"№{it['doc_name']}", 'severity': 'warning',
             'detail': f"не удалось проверить: {it['error']}"}
            for it in self.stats['stuck_production_failed']
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
            ('supply_jumps',      'Скачки цен в приёмках',        ['supply_jumps']),
            ('codes',             'Коды товаров',                 ['code_no_code', 'code_duplicates', 'code_suspect']),
            ('stale_drafts',      'Незавершённые черновики',      ['stale_drafts']),
            ('stuck_production',  'Зависшие производственные задания', ['stuck_production']),
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

        # Сводка
        sev_counts = {'critical': 0, 'important': 0, 'warning': 0}
        cat_counts = {}
        for cat in categories:
            cat_counts[cat['key']] = cat['count']
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
                # Внутри summary, потому что ingest сохраняет в БД только summary и categories
                'checks': checks_grid,
            },
            'categories': categories,
        }

        with open(path, 'w', encoding='utf-8') as f:
            _json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"\n📄 Результаты сохранены: {path}")
