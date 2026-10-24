from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from api.models import UserPageAccess, UserPageEvent
from core.models import Counterparty, Product, Shipment, ShipmentItem


class HomeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('ivan', password='password', first_name='Иван')
        self.client.force_login(self.user)

    def _grant(self, *keys):
        for key in keys:
            UserPageAccess.objects.create(user=self.user, page_key=key)

    def _visit(self, path, times=1):
        for _ in range(times):
            UserPageEvent.objects.create(user=self.user, page_path=path, page_name='', duration_seconds=10)

    def _home(self):
        response = self.client.get('/api/auth/home/')
        self.assertEqual(response.status_code, 200)
        return response.json()['data']

    def test_requires_authentication(self):
        self.client.logout()
        self.assertEqual(self.client.get('/api/auth/home/').status_code, 401)

    def test_visits_follow_sections_and_access(self):
        self._grant('inventory', 'abc')
        self._visit('/analysis/abc', times=2)
        self._visit('/inventory/cells', times=3)
        self._visit('/deadlines', times=9)

        data = self._home()

        self.assertEqual(data['sectionVisits'], {'inventory': 3, 'abc': 2})
        self.assertEqual(data['frequentPaths'], ['/inventory', '/analysis/abc'])

    def test_pulse_is_hidden_without_shipments_access(self):
        self._grant('raw-materials')

        self.assertIsNone(self._home()['pulse'])

    def test_pulse_sums_goods_like_the_shipments_section(self):
        self._grant('shipments-products')
        counterparty = Counterparty.objects.create(name='КСК', external_id='c-1')
        product = Product.objects.create(name='Биотин', external_id='p-1', group='Товары', subgroup='ExterPro')
        box = Product.objects.create(name='Коробка', external_id='p-2', group='Тара')
        no_subgroup = Product.objects.create(name='Без подгруппы', external_id='p-3', group='Товары', subgroup='')
        now = timezone.now()
        today = Shipment.objects.create(counterparty=counterparty, external_id='s-1', date=now)
        ShipmentItem.objects.create(shipment=today, product=product, quantity=Decimal('2'), price=Decimal('1320'))
        ShipmentItem.objects.create(shipment=today, product=box, quantity=Decimal('3'), price=Decimal('50'))
        ShipmentItem.objects.create(shipment=today, product=no_subgroup, quantity=Decimal('1'), price=Decimal('700'))
        gone = Shipment.objects.create(counterparty=counterparty, external_id='s-2', date=now, deleted_at=now)
        ShipmentItem.objects.create(shipment=gone, product=product, quantity=Decimal('5'), price=Decimal('1000'))
        old = Shipment.objects.create(counterparty=counterparty, external_id='s-3', date=now - timedelta(days=40))
        ShipmentItem.objects.create(shipment=old, product=product, quantity=Decimal('1'), price=Decimal('999'))

        points = self._home()['pulse']['points']

        self.assertEqual(len(points), 30)
        self.assertEqual(points[-1], {'date': timezone.localdate().isoformat(), 'value': 2640})
        self.assertEqual(sum(point['value'] for point in points), 2640)
