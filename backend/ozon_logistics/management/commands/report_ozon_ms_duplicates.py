"""Отчёт по дублям в МойСклад: наш заказ сайта против заказа от синхронизации Ozon."""

from django.core.management.base import BaseCommand

from ozon_logistics.services.ms_duplicates import MoyskladError, find_duplicates


class Command(BaseCommand):
    help = 'Показать дубли заказов в МойСклад по отправлениям Ozon Доставки (ничего не меняет)'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20,
                            help='Сколько последних отправлений проверить')

    def handle(self, *args, **options):
        try:
            pairs = find_duplicates(limit=options['limit'])
        except MoyskladError as exc:
            self.stderr.write(self.style.ERROR(str(exc)))
            return

        if not pairs:
            self.stdout.write('Отправлений Ozon пока нет — проверять нечего')
            return

        with_duplicates = 0
        for pair in pairs:
            self.stdout.write('')
            self.stdout.write(
                f"Отправление {pair['posting_number']} · {pair['posting_status'] or 'без статуса'}"
            )

            ours = pair['site_order']
            if ours:
                self.stdout.write(
                    f"  наш заказ сайта:  №{ours['name']} · {ours['sum']:.2f} ₽ · "
                    f"оплачено {ours['paid']:.2f} ₽"
                )
            else:
                self.stdout.write(self.style.WARNING('  наш заказ сайта: не найден'))

            if not pair['duplicates']:
                self.stdout.write('  дублей не найдено')
                continue

            with_duplicates += 1
            for duplicate in pair['duplicates']:
                self.stdout.write(self.style.WARNING(
                    f"  дубль:            №{duplicate['name']} · {duplicate['sum']:.2f} ₽ · "
                    f"{duplicate['description'] or 'без комментария'}"
                ))

        self.stdout.write('')
        self.stdout.write(
            f'Проверено отправлений: {len(pairs)}, с дублями: {with_duplicates}'
        )
        self.stdout.write('Ничего не изменено — это отчёт.')
