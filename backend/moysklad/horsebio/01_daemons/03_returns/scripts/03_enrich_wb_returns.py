#!/usr/bin/env python3
"""
Простановка статуса и комментария на черновиках возвратов ВБ.

Черновики возвратов ВБ заводит монитор (01_monitor_returns.py) по статусу заказа.
До сих пор они висели без всякого признака того, где товар — считалось, что из API
Вайлдберриз это недоступно. Доступно: отчёт /api/v1/analytics/goods-return отдаёт
физический статус возврата и пункт выдачи, а сопоставляется он с МойСкладом по
номеру задания ВБ, который синхронизация пишет в описание заказа.

Вся общая механика — в returns_enrich.py, данные ВБ — в wb_returns.py.

Запуск:
  python3 03_enrich_wb_returns.py            # проставить статусы
  python3 03_enrich_wb_returns.py --dry-run  # показать, ничего не писать
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import returns_enrich  # noqa: E402
import wb_returns  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Статусы черновиков возвратов ВБ по отчёту Wildberries")
    ap.add_argument('--dry-run', action='store_true', help="Показать, ничего не писать в МС")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()
    returns_enrich.run(wb_returns, dry_run=args.dry_run, results_out=args.results_out, days_back=210)


if __name__ == '__main__':
    main()
