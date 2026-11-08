class ConsoleReportMixin:
    def print_report(self):
        """Вывести отчёт"""

        print("\n" + "="*70)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("="*70 + "\n")

        self.report_fifo()
        self.report_enter_prices()
        self.report_negative_stock()
        self.report_enters()
        self.report_losses()
        self.report_inventory_prices()
        self.report_inventories()
        self.report_moves()
        self.report_supplies()
        self.report_supply_jumps()

        # Статистика
        print(f"\n{'='*70}")
        print("СТАТИСТИКА:")
        self.summary_fifo()
        self.summary_enter_prices()
        self.summary_negative_stock()
        self.summary_enters()
        self.summary_losses()
        self.summary_inventories()
        self.summary_inventory_prices()
        self.summary_moves()
        self.summary_supplies()
        self.summary_supply_jumps()
        self.summary_codes()
        self.summary_enter_zero()
        self.summary_stale_drafts()
        self.summary_stuck_production()
        print("="*70 + "\n")
