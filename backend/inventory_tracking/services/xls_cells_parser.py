"""
Parser for МойСклад 'Инвентаризация с ячейками' XLS export.
Template: inventory-address-warehouse-by-slot

Expected structure:
  Row N:   Инвентаризация: | <empty> | 00022
  Row N+1: Дата проведения: | <empty> | <excel serial date>
  Row N+2: Склад: | <empty> | Шатл - склад сырья + тары
  ...
  Header row: ... | № | Код | Наименование | Ячейка | ...
  Data rows:  ... | 0  | 1-164 | Хондроитин сульфат | А/A6 | ...
  Last row:   ... | | | | Итого: | ...
"""
import logging
from datetime import date, datetime

import xlrd

logger = logging.getLogger(__name__)


def parse_cells_inventory_xls(file_obj) -> dict:
    """
    Parse one XLS file from МойСклад 'Инвентаризация с ячейками' export.

    Returns:
        {
            'inventory_name': '00022',        # document number
            'inventory_date': date object,    # date of the inventory
            'warehouse': 'Шатл - ...',
            'articles': ['1-164', '4-112'],   # article codes (Код column)
        }
    Raises ValueError if the file structure is unrecognised.
    """
    wb = xlrd.open_workbook(file_contents=file_obj.read())
    ws = wb.sheet_by_index(0)

    result = {
        'inventory_name': None,
        'inventory_date': None,
        'warehouse': None,
        'codes': [],      # МойСклад product code field (column «Код» in XLS)
    }

    header_row_idx = None
    article_col_idx = None

    for row_idx in range(ws.nrows):
        row_vals = [str(ws.cell(row_idx, c).value).strip() for c in range(ws.ncols)]

        # ── Metadata rows ──────────────────────────────────────────────────
        for col_idx, val in enumerate(row_vals):
            if val == 'Инвентаризация:':
                for c in range(col_idx + 1, len(row_vals)):
                    if row_vals[c]:
                        result['inventory_name'] = row_vals[c]
                        break

            elif val == 'Дата проведения:':
                for c in range(col_idx + 1, len(row_vals)):
                    if row_vals[c]:
                        try:
                            serial = float(row_vals[c])
                            dt_tuple = xlrd.xldate_as_tuple(serial, wb.datemode)
                            result['inventory_date'] = date(*dt_tuple[:3])
                        except (ValueError, TypeError):
                            pass
                        break

            elif val == 'Склад:':
                for c in range(col_idx + 1, len(row_vals)):
                    if row_vals[c]:
                        result['warehouse'] = row_vals[c]
                        break

        # ── Header row detection ───────────────────────────────────────────
        if 'Код' in row_vals and 'Наименование' in row_vals:
            header_row_idx = row_idx
            article_col_idx = row_vals.index('Код')
            continue

        # ── Data rows ──────────────────────────────────────────────────────
        if header_row_idx is not None and article_col_idx is not None:
            if row_idx <= header_row_idx:
                continue
            raw = ws.cell(row_idx, article_col_idx).value
            article = str(raw).strip() if raw else ''
            # Skip empty cells, numeric-only values (serial numbers), and totals
            if article and article not in ('0.0', '0') and not article.replace('.', '').isdigit():
                result['codes'].append(article)

    if not result['codes'] and header_row_idx is None:
        raise ValueError(
            'Файл не соответствует шаблону «Инвентаризация с ячейками». '
            'Убедитесь, что выбран шаблон inventory-address-warehouse-by-slot.'
        )

    logger.info(
        f"Parsed cells inventory: name={result['inventory_name']}, "
        f"date={result['inventory_date']}, codes={len(result['codes'])}"
    )
    return result


def apply_cells_upload(run, codes: list, inventory_date: date) -> int:
    """
    Merge XLS data into an existing InventoryRun.

    For each ProductInventoryStatus in `run` whose code matches one in
    `codes` (МойСклад product code from the «Код» column), mark it
    inventoried and bump the counter.
    Returns the number of updated records.
    """
    from django.utils import timezone

    if not codes:
        return 0

    statuses = list(run.products.filter(code__in=codes))
    if not statuses:
        return 0

    now = timezone.now()
    inv_dt = timezone.make_aware(
        datetime.combine(inventory_date, datetime.min.time())
    )

    # Use month-end as reference for completed months (same logic as inventory_checker)
    from inventory_tracking.services.inventory_checker import _last_day_of_month
    if run.is_month_snapshot:
        month_end = _last_day_of_month(run.month_start)
        reference_dt = timezone.make_aware(
            datetime.combine(month_end, datetime.max.time().replace(microsecond=0))
        )
    else:
        reference_dt = now

    to_update = []
    for s in statuses:
        s.is_inventoried = True
        s.inventory_count = (s.inventory_count or 0) + 1
        if s.last_inventoried_at is None or inv_dt > s.last_inventoried_at:
            s.last_inventoried_at = inv_dt
            s.days_since_last = (reference_dt - inv_dt).days
        to_update.append(s)

    from inventory_tracking.models import ProductInventoryStatus
    ProductInventoryStatus.objects.bulk_update(
        to_update,
        ['is_inventoried', 'inventory_count', 'last_inventoried_at', 'days_since_last'],
    )

    # Recalculate run totals
    total = run.products.count()
    inventoried = run.products.filter(is_inventoried=True).count()
    run.inventoried_count = inventoried
    run.not_inventoried_count = total - inventoried
    run.save(update_fields=['inventoried_count', 'not_inventoried_count'])

    logger.info(
        f"Cells upload: run #{run.id} [{run.month_start}] — "
        f"matched {len(to_update)}/{len(codes)} codes. "
        f"Run totals: {inventoried}/{total}"
    )
    return len(to_update)
