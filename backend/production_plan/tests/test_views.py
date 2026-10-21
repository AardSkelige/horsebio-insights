from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone

from api.models import SectionSnapshot, UserPageAccess
from production_plan.models import Exclusion, GreenItem, OzonMonthSales
from production_plan.services.plan import full_months

STOCK = {'generated_at': '2026-10-21T06:00:00+00:00', 'store': 'Склад готовой продукции', 'items': [
    {'article': '11-36AP0100', 'name': 'Капсулы', 'quantity': 100, 'in_transit': 0},
    {'article': '08-10EP5000', 'name': 'Льняное масло', 'quantity': 0, 'in_transit': 0},
]}


class ProductionPlanApiTests(TestCase):
    def setUp(self):
        user = User.objects.create_user('arseniy', password='secret')
        self.client = Client()
        self.client.login(username='arseniy', password='secret')
        self.access = UserPageAccess.objects.create(user=user, page_key='production-plan')
        SectionSnapshot.store('fbo-stock', STOCK)
        for month in full_months(timezone.localdate()):
            OzonMonthSales.objects.create(month=month, article='11-36AP0100', quantity=300)
            OzonMonthSales.objects.create(month=month, article='08-10EP5000', quantity=4)

    def test_closed_without_page_access(self):
        self.access.delete()
        self.assertEqual(self.client.get('/api/production-plan/').status_code, 403)

    def test_plan(self):
        rows = self.client.get('/api/production-plan/').json()['rows']
        self.assertEqual([(r['article'], r['produce'], r['status']) for r in rows], [
            ('08-10EP5000', 8, 'urgent'), ('11-36AP0100', 500, 'produce'),
        ])

    def test_exclusion_hides_and_returns(self):
        response = self.client.post('/api/production-plan/exclusions/', {'text': '  масло '}, content_type='application/json')
        rule = response.json()['items'][0]
        self.assertEqual(rule['text'], 'масло')
        self.assertEqual(len(self.client.get('/api/production-plan/').json()['rows']), 1)
        self.client.delete(f"/api/production-plan/exclusions/{rule['id']}/")
        self.assertFalse(Exclusion.objects.exists())

    def test_empty_exclusion_refused(self):
        self.assertEqual(self.client.post('/api/production-plan/exclusions/', {'text': ' '}, content_type='application/json').status_code, 400)

    def test_too_long_refused(self):
        response = self.client.post('/api/production-plan/exclusions/', {'text': 'я' * 300}, content_type='application/json')
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/production-plan/green/', {'article': 'A' * 70}, content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_green_toggle(self):
        self.client.post('/api/production-plan/green/', {'article': '11-36ap0100', 'name': 'Капсулы'}, content_type='application/json')
        rows = {r['article']: r for r in self.client.get('/api/production-plan/').json()['rows']}
        self.assertTrue(rows['11-36AP0100']['green'])
        self.client.delete('/api/production-plan/green/', {'article': '11-36AP0100'}, content_type='application/json')
        self.assertFalse(GreenItem.objects.exists())

    def test_excel(self):
        response = self.client.get('/api/production-plan/export/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'PK'))

    def test_refresh_reports_ozon_failure(self):
        from api.services.ozon_stock import OzonStockError
        with patch('production_plan.views.fbo_stock.get_data'), \
             patch('production_plan.views.ozon_sales.sync', side_effect=OzonStockError('нет ключа')):
            response = self.client.post('/api/production-plan/refresh/')
        self.assertEqual(response.status_code, 502)
        self.assertIn('нет ключа', response.json()['error'])

    def test_refresh_does_not_wait_long_for_ozon(self):
        from api.services.ozon_stock import QUICK_PAUSES
        with patch('production_plan.views.fbo_stock.get_data', return_value=STOCK), \
             patch('production_plan.views.ozon_sales.sync') as sync:
            self.client.post('/api/production-plan/refresh/')
        self.assertEqual(sync.call_args.args[1], QUICK_PAUSES)
        self.assertLess(sum(QUICK_PAUSES), 10)
