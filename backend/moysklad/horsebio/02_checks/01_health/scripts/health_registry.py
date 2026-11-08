def _check(id, title, report=(), summary=(), export=(), full_only=False):
    return {'id': id, 'title': title, 'report': list(report), 'summary': list(summary),
            'export': list(export), 'full_only': full_only}


CHECKS = [
    _check('deviations', 'Отклонения FIFO vs приёмка',
           ['report_fifo'], ['summary_fifo'], ['export_fifo']),
    _check('negative_stock', 'Отрицательные остатки',
           ['report_negative_stock'], ['summary_negative_stock'], ['export_negative_stock']),
    _check('enters', 'Оприходования: внутр. склады',
           ['report_enters'], ['summary_enters'], ['export_enters']),
    _check('enter_prices', 'Оприходования: цена ≠ приёмка',
           ['report_enter_prices'], ['summary_enter_prices'], ['export_enter_prices']),
    _check('enter_zero', 'Оприходования: нулевые цены',
           [], ['summary_enter_zero'], ['export_enter_zero']),
    _check('losses', 'Списания',
           ['report_losses'], ['summary_losses'], ['export_losses']),
    _check('inventories', 'Инвентаризации',
           ['report_inventory_prices', 'report_inventories'],
           ['summary_inventories', 'summary_inventory_prices'],
           ['export_inventories', 'export_inventory_prices']),
    _check('moves', 'Перемещения',
           ['report_moves'], ['summary_moves'], ['export_moves']),
    _check('supplies', 'Приёмки',
           ['report_supplies'], ['summary_supplies'], ['export_supplies']),
    _check('supply_jumps', 'Скачки цен в приёмках',
           ['report_supply_jumps'], ['summary_supply_jumps'], ['export_supply_jumps'], full_only=True),
    _check('codes', 'Коды товаров',
           [], ['summary_codes'], ['export_codes']),
    _check('stale_drafts', 'Незавершённые черновики',
           [], ['summary_stale_drafts'], ['export_stale_drafts']),
    _check('stuck_production', 'Зависшие производственные задания',
           [], ['summary_stuck_production'], ['export_stuck_production']),
]


def check_runs(check, full_mode):
    return full_mode or not check['full_only']
