import base64
import json
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase

from api.notifications.production_plan import production_plan_notifications
from production_plan.models import WbSync

TODAY = date(2026, 10, 21)


def token(expires):
    payload = base64.urlsafe_b64encode(json.dumps({'exp': int(datetime(expires.year, expires.month, expires.day, 12).timestamp())}).encode()).decode().rstrip('=')
    return f'head.{payload}.sign'


def loaded(on):
    WbSync.objects.create(covered_from=date(2026, 7, 24))
    WbSync.objects.update(synced_at=datetime(on.year, on.month, on.day, 7, tzinfo=dt_timezone.utc))


def collect(key):
    with patch.dict('os.environ', {'WB_STATS_TOKEN': key}), \
         patch('api.notifications.production_plan.timezone.localdate', return_value=TODAY):
        return list(production_plan_notifications())


class WbNotificationTests(TestCase):
    def test_quiet_when_fresh_and_key_far(self):
        loaded(TODAY)
        self.assertEqual(collect(token(date(2027, 4, 21))), [])

    def test_stale_loading(self):
        loaded(date(2026, 10, 17))
        items = collect(token(date(2027, 4, 21)))
        self.assertEqual([i.key for i in items], ['production-plan:wb-stale'])
        self.assertEqual(items[0].body, 'Последняя загрузка 17.10.2026')

    def test_key_expiring_then_expired(self):
        loaded(TODAY)
        self.assertEqual([(i.key, i.level) for i in collect(token(date(2026, 11, 10)))], [('production-plan:wb-key', 'warning')])
        self.assertEqual([(i.key, i.level) for i in collect(token(date(2026, 10, 20)))], [('production-plan:wb-key', 'critical')])

    def test_silent_without_key(self):
        with patch.dict('os.environ', {'WB_STATS_TOKEN': ''}):
            self.assertEqual(list(production_plan_notifications()), [])
