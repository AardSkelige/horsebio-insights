#!/usr/bin/env python3
"""
Простановка статуса и комментария на черновиках возвратов Озон.

Монитор (01_monitor_returns.py) заводит черновик на каждый возврат, который едет
к нам. Этот скрипт отвечает на вопрос «где коробка сейчас»: тянет статус из Ozon
API и раскладывает черновики по статусам МС — чтобы в списке возвратов было видно
глазами, что забрать в ПВЗ, что разобрать на складе и что пинать в поддержке.

Раньше скрипт удалял черновики, уезжающие на склад Озона. Так мы потеряли два
документа (заказы 06405 и 06469): Озон переназначил конечную точку на наш ПВЗ уже
после удаления. Теперь удаление наступает, только когда возврат физически доехал
до склада Озона и прошло 30 дней — до тех пор документ живёт со статусом
«Ушёл на склад МП».

Вся общая механика — в returns_enrich.py, данные Ozon — в ozon_returns.py.

Запуск:
  python3 02_enrich_ozon_returns.py            # проставить статусы
  python3 02_enrich_ozon_returns.py --dry-run  # показать, ничего не писать
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ozon_returns  # noqa: E402
import returns_enrich  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Статусы черновиков возвратов Озон по данным Ozon API")
    ap.add_argument('--dry-run', action='store_true', help="Показать, ничего не писать в МС")
    ap.add_argument('--results-out', type=str, default=None,
                    help="Путь для структурированного JSON находок (для страницы /checks)")
    args = ap.parse_args()
    returns_enrich.run(ozon_returns, dry_run=args.dry_run, results_out=args.results_out)


if __name__ == '__main__':
    main()
