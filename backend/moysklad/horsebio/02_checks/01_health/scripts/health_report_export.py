from health_registry import CHECKS, check_runs


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

        checks_grid = []
        for check in CHECKS:
            check_id, title = check['id'], check['title']
            if not check_runs(check, getattr(self, 'full_mode', False)):
                checks_grid.append({'id': check_id, 'title': title, 'status': 'skipped',
                                    'count': 0, 'severity': None, 'cats': []})
                continue
            start = len(categories)
            for name in check['export']:
                getattr(self, name)(add)
            present = [c for c in categories[start:] if c['severity'] != 'ok']
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
