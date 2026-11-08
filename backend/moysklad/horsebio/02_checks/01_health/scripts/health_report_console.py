from health_registry import CHECKS, check_runs


class ConsoleReportMixin:
    def _running_checks(self):
        return [c for c in CHECKS if check_runs(c, getattr(self, 'full_mode', False))]

    def print_report(self):
        """Вывести отчёт"""

        print("\n" + "="*70)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("="*70 + "\n")

        for check in self._running_checks():
            for name in check['report']:
                getattr(self, name)()

        # Статистика
        print(f"\n{'='*70}")
        print("СТАТИСТИКА:")
        for check in self._running_checks():
            for name in check['summary']:
                getattr(self, name)()
        print("="*70 + "\n")
