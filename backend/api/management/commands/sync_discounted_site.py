"""Синхронизация уценки с сайтом: остатки, цены и снятие с продажи по сроку.

Запускается по расписанию. Делает две вещи:

* отправляет на сайт актуальные цены и остатки по опубликованным позициям —
  продали две банки, и на витрине стало на две меньше;
* снимает с продажи то, у чего до конца срока осталось меньше двух месяцев.
  Это правило из регламента (docs/ucenka.md), и оно должно срабатывать само,
  а не когда человек заглянет на страницу.

Карточки, которых ещё нет на сайте, пропускаются: публикация — осознанное
действие человека, кнопкой на странице «Уценка».
"""

from django.core.management.base import BaseCommand

from api.services import site_exchange
from api.views.discounted import (
    STATE_DELIST, STATE_EXPIRED, _build_data,
)


class Command(BaseCommand):
    help = "Отправить на сайт остатки уценки и снять с продажи просроченное"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true",
                            help="показать, что было бы отправлено, и ничего не делать")

    def handle(self, *args, **options):
        data = _build_data()
        published = [p for p in data["positions"] if p.get("published")]
        if not published:
            self.stdout.write("На сайте нет опубликованных позиций уценки — нечего синхронизировать")
            return

        stock = [{
            "id": p["id"],
            "article": p["article"],
            "name": p["name"],
            "price": int(round(p["price"])),
            "quantity": int(p["quantity"]),
        } for p in published]

        # Снимаем то, что дожило до порога: продавать такой товар уже нельзя,
        # покупателю не хватит срока на курс и доставку
        expiring = [p for p in published if p["state"] in (STATE_EXPIRED, STATE_DELIST)]

        if options["dry_run"]:
            for item in stock:
                self.stdout.write(f"остаток  {item['article']}: {item['quantity']} шт по {item['price']} ₽")
            for p in expiring:
                self.stdout.write(f"снять    {p['article']}: осталось {p['days_left']} дн")
            return

        site_exchange.push_stock(stock)
        self.stdout.write(f"Отправлены цены и остатки: {len(stock)} позиций")

        for position in expiring:
            site_exchange.set_visibility(
                product_id=position["id"],
                article=position["article"],
                name=position["name"],
                visibility=site_exchange.HIDDEN_404,
            )
            self.stdout.write(self.style.WARNING(
                f"Снята с продажи {position['article']}: осталось {position['days_left']} дн"
            ))
