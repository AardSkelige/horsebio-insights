from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from api.models import UserPageAccess
from raw_materials.models import Slot
from raw_materials.tests.factories import batch, material, stock

URL = '/api/raw-materials/'


class RawMaterialsPageApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('arseniy', password='secret')
        self.client = Client()
        self.client.login(username='arseniy', password='secret')

    def grant(self):
        UserPageAccess.objects.create(user=self.user, page_key='raw-materials')

    def test_closed_without_page_access(self):
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_lists_stock_with_live_batches(self):
        self.grant()
        chondroitin = material()
        stock(chondroitin, '120', slot=Slot.objects.create(external_id='s', name='A5'))
        batch(chondroitin, '100', series='0425', expiry=(2027, 3, 1))
        batch(chondroitin, '20')
        batch(chondroitin, '0', series='old')
        stock(material('Пустое'), '0')

        items = self.client.get(URL).json()['items']

        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]['slot'], items[0]['quantity']), ('A5', 120.0))
        self.assertEqual([b['series'] for b in items[0]['batches']], ['0425', ''])

    def test_refresh_syncs_with_moysklad(self):
        self.grant()
        with patch('raw_materials.views.sync_from_moysklad') as sync, patch('raw_materials.views.pull_supplies') as pull:
            response = self.client.post(f'{URL}refresh/')
        sync.assert_called_once()
        pull.assert_called_once()
        self.assertEqual(response.status_code, 200)
