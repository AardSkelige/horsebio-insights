import glob
import importlib
import os
import sys

from django.test import SimpleTestCase

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', '..', 'moysklad', 'horsebio',
                       '02_checks', '01_health', 'scripts')
sys.path.insert(0, SCRIPTS)

from health_registry import CHECKS  # noqa: E402

KINDS = ('report', 'summary', 'export')
NOT_CHECKS = {'health_registry', 'health_config', 'health_format',
              'health_report_console', 'health_report_export'}


def mixin_methods():
    names = set()
    for path in glob.glob(os.path.join(SCRIPTS, 'health_*.py')):
        module_name = os.path.basename(path)[:-3]
        if module_name in NOT_CHECKS:
            continue
        module = importlib.import_module(module_name)
        for obj in vars(module).values():
            if isinstance(obj, type) and obj.__module__ == module_name:
                names.update(n for n in vars(obj) if n.startswith(tuple(f'{k}_' for k in KINDS)))
    return names


class HealthRegistryTests(SimpleTestCase):
    def test_every_registered_method_exists(self):
        defined = mixin_methods()
        for check in CHECKS:
            for kind in KINDS:
                for name in check[kind]:
                    self.assertIn(name, defined, f"{check['id']}: нет метода {name}")

    def test_every_report_method_is_registered(self):
        registered = {name for check in CHECKS for kind in KINDS for name in check[kind]}
        self.assertEqual(mixin_methods() - registered, set())

    def test_every_check_has_summary_and_export(self):
        for check in CHECKS:
            self.assertTrue(check['summary'], check['id'])
            self.assertTrue(check['export'], check['id'])

    def test_check_ids_are_unique(self):
        ids = [c['id'] for c in CHECKS]
        self.assertEqual(len(ids), len(set(ids)))
