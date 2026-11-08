from health_config import SHEET_PRICED_SUPPLIERS, SHEET_PRICE


class SheetPriceChecksMixin:
    # Цена наклейки равна цене листа, умноженной на 1 или 2 (комплект) и делённой на число наклеек на листе
    SHEET_LAYOUTS = range(3, 41)
    SHEET_PRICE_RANGE = (90.0, 160.0)
    SHEET_INFER_MIN_LINES = 3

    def _is_sheet_priced(self, row):
        agent = self._short_agent(row)
        return any(s in agent for s in SHEET_PRICED_SUPPLIERS)

    @classmethod
    def _sheet_fit(cls, price, sheet):
        tol = max(0.011, price * 0.002)
        for n in cls.SHEET_LAYOUTS:
            for k in (1, 2):
                if abs(price - sheet * k / n) <= tol:
                    return n, k
        return None

    @classmethod
    def _doc_sheet_price(cls, lines):
        if len(lines) < cls.SHEET_INFER_MIN_LINES:
            return SHEET_PRICE
        lo, hi = cls.SHEET_PRICE_RANGE
        candidates = {round(l['price'] * n / k, 2)
                      for l in lines for n in cls.SHEET_LAYOUTS for k in (1, 2)
                      if lo <= l['price'] * n / k <= hi}
        if not candidates:
            return SHEET_PRICE
        return max(sorted(candidates), key=lambda c: sum(1 for l in lines if cls._sheet_fit(l['price'], c)))

    def _sheet_doc_lines(self, href):
        doc_id = href.rstrip('/').split('/')[-1].split('?')[0]
        rows = self.h._get_all_pages(f"/entity/supply/{doc_id}/positions", {"expand": "assortment"})
        lines = []
        for r in rows:
            a = r.get('assortment') or {}
            price = (r.get('price', 0) or 0) / 100
            if (a.get('name') or '').startswith('Наклейка') and price > 0:
                lines.append({'name': a['name'], 'code': (a.get('code') or '').strip(),
                              'quantity': r.get('quantity', 0), 'price': price})
        return lines

    def check_sheet_prices(self, sheet_docs):
        misses = {}
        for href, doc in sheet_docs.items():
            lines = self._sheet_doc_lines(href)
            sheet = self._doc_sheet_price(lines)
            for l in lines:
                if not self._sheet_fit(l['price'], sheet):
                    misses.setdefault(l['code'] or l['name'], []).append((doc, l, sheet, len(lines)))

        results = []
        for found in misses.values():
            found.sort(key=lambda m: m[0]['moment'], reverse=True)
            doc, l, sheet, n_lines = found[0]
            results.append({
                'name': l['name'], 'code': l['code'], 'basis': 'sheet', 'sheet_price': sheet,
                'lines_in_doc': n_lines, 'other_docs': [m[0]['name'] for m in found[1:]],
                'last_price': l['price'], 'last_qty': l['quantity'], 'last_agent': doc['agent'],
                'prev_agents': [], 'avg_prev': sheet, 'jump_pct': 0.0,
                'last_doc': doc['name'], 'last_date': doc['moment'][:10],
                'history': [], 'auto_reason': None,
            })
        return results
