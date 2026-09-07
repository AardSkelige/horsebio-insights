"""Синхронизация уценки с Ozon: остаток на витрине равен остатку в МойСклад.

Ozon продаёт уценку с нашего склада (FBS), а остаток на витрине до 07.09.2026
вёлся руками — площадка не смотрит в МойСклад вовсе. Из-за этого заказы
приходили на товар, которого уже нет: на витрине Ozon стояло 38 штук, на сайте
те же 40, а физически партия одна.

Теперь истина одна — МойСклад:

* отправляем доступный остаток (что на складе минус то, что уже в резерве под
  принятые заказы Ozon и сайта);
* обнуляем остаток по позициям, которые пора снимать с продажи — до конца срока
  меньше двух месяцев или он уже вышел. Это правило регламента (docs/ucenka.md),
  и на Ozon оно должно срабатывать само: там к сроку доставки добавляются дни
  на логистику площадки.

Позиции, не заведённые на Ozon, пропускаем: на сайте уценки больше, и это норма.
"""

from django.core.management.base import BaseCommand

from api.services import ozon_stock
from api.views.discounted import STATE_DELIST, STATE_EXPIRED, positions_snapshot


class Command(BaseCommand):
    help = "Отправить на Ozon остатки уценки из МойСклад"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="показать, что было бы отправлено, и ничего не делать")

    def handle(self, *args, **options):
        # refresh: остаток нужен свежий, а не пятиминутной давности из кеша страницы
        positions = positions_snapshot(refresh=True)
        if not positions:
            self.stdout.write("В группе «Уценка» нет карточек — синхронизировать нечего")
            return

        wanted = {}
        for position in positions:
            article = position.get("article")
            if not article:
                continue
            if position["state"] in (STATE_EXPIRED, STATE_DELIST):
                wanted[article] = 0
            else:
                available = (position.get("quantity") or 0) - (position.get("reserve") or 0)
                wanted[article] = max(int(available), 0)

        on_ozon = ozon_stock.known_offers(wanted)
        skipped = sorted(set(wanted) - on_ozon)
        items = [{"offer_id": article, "stock": stock}
                 for article, stock in sorted(wanted.items()) if article in on_ozon]

        if not items:
            self.stdout.write("На Ozon нет ни одной уценённой карточки — отправлять нечего")
            return

        if options["dry_run"]:
            for item in items:
                self.stdout.write(f"остаток  {item['offer_id']}: {item['stock']} шт")
            for article in skipped:
                self.stdout.write(f"пропуск  {article}: нет карточки на Ozon")
            return

        warehouse = ozon_stock.warehouse_id()
        failures = ozon_stock.push_stock(items, warehouse)

        self.stdout.write(
            "Отправлено на Ozon: {} позиций ({})".format(
                len(items) - len(failures),
                ", ".join(f"{i['offer_id']} → {i['stock']}" for i in items),
            )
        )
        for article in skipped:
            self.stdout.write(f"Нет карточки на Ozon, пропущено: {article}")
        for article, error in failures:
            self.stderr.write(self.style.ERROR(f"Ozon не принял остаток {article}: {error}"))
