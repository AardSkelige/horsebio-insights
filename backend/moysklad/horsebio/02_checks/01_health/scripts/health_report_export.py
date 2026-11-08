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

        def add(key, title, kind, ms_type, items):
            if not items:
                return
            sev = max((it['severity'] for it in items),
                      key=lambda s: self._SEVERITY_RANK.get(s, 0))
            categories.append({
                'key': key, 'title': title, 'kind': kind, 'ms_type': ms_type,
                'severity': sev, 'count': len(items), 'items': items,
            })

        self.export_fifo(add)
        self.export_enter_prices(add)
        self.export_negative_stock(add)
        self.export_enters(add)
        self.export_losses(add)
        self.export_inventories(add)
        self.export_inventory_prices(add)
        self.export_moves(add)
        self.export_supplies(add)
        self.export_enter_zero(add)
        self.export_supply_jumps(add)
        self.export_codes(add)
        self.export_stale_drafts(add)
        self.export_stuck_production(add)

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
