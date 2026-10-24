import json
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from pywebpush import WebPushException

from api.models import NotificationState, PushDelivery, PushSubscription, UserPageAccess
from api.notifications import core, push


def _note(key, level=core.WARNING, title=None, fingerprint='v1'):
    return core.Notification(key=key, level=level, title=title or key, body='Подробности', fingerprint=fingerprint)


class PushTest(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.items = {'discounted': [], 'raw-materials': []}
        providers = {source: (lambda s=source: list(self.items[s])) for source in self.items}
        patcher = patch.dict(core._PROVIDERS, providers, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sent = []
        sender = patch('api.notifications.push.webpush', side_effect=lambda **kw: self.sent.append(kw))
        sender.start()
        self.addCleanup(sender.stop)
        self.user = User.objects.create_user('ivan', password='x')
        UserPageAccess.objects.create(user=self.user, page_key='discounted')
        self.device = PushSubscription.objects.create(
            user=self.user, endpoint='https://fcm.googleapis.com/fcm/send/ivan', p256dh='key', auth='auth',
        )

    def _payloads(self):
        return [json.loads(call['data']) for call in self.sent]

    def _dispatch(self):
        cache.clear()
        return push.dispatch()

    def test_new_notification_is_pushed_once(self):
        self.items['discounted'] = [_note('discounted:delist:p1', title='Пора снимать с продажи')]

        self._dispatch()
        self._dispatch()

        payload, = self._payloads()
        self.assertEqual(payload['title'], 'Пора снимать с продажи')
        self.assertEqual(payload['url'], '/discounted')

    def test_changed_essence_is_pushed_again(self):
        self.items['discounted'] = [_note('discounted:delist:p1')]
        self._dispatch()
        self.items['discounted'] = [_note('discounted:delist:p1', fingerprint='v2')]

        self._dispatch()

        self.assertEqual(len(self.sent), 2)

    def test_closed_and_returned_condition_is_pushed_again(self):
        self.items['discounted'] = [_note('discounted:delist:p1')]
        self._dispatch()
        self.items['discounted'] = []
        self._dispatch()
        self.items['discounted'] = [_note('discounted:delist:p1')]

        self._dispatch()

        self.assertEqual(len(self.sent), 2)

    def test_section_without_access_is_not_pushed(self):
        self.items['raw-materials'] = [_note('raw:expired:1')]

        self._dispatch()

        self.assertEqual(self.sent, [])

    def test_already_read_in_the_bell_is_not_pushed(self):
        self.items['discounted'] = [_note('discounted:delist:p1')]
        NotificationState.objects.create(user=self.user, key='discounted:delist:p1', fingerprint='v1', seen_at='2026-10-24T10:00:00Z')

        self._dispatch()

        self.assertEqual(self.sent, [])

    def test_several_new_go_in_one_push_led_by_the_most_serious(self):
        self.items['discounted'] = [
            _note('discounted:a', level=core.INFO, title='К сведению'),
            _note('discounted:b', level=core.CRITICAL, title='Просрочено'),
            _note('discounted:c'),
        ]

        self._dispatch()

        payload, = self._payloads()
        self.assertEqual(payload['title'], '3 новых дела')
        self.assertEqual(payload['body'], 'Просрочено')

    def test_subscribing_does_not_dump_what_was_already_there(self):
        self.device.delete()
        self.items['discounted'] = [_note('discounted:old')]
        client = Client()
        client.force_login(self.user)

        response = client.post('/api/push/subscribe/', {
            'endpoint': 'https://fcm.googleapis.com/fcm/send/phone', 'keys': {'p256dh': 'k', 'auth': 'a'},
        }, content_type='application/json')
        self._dispatch()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sent, [])
        self.items['discounted'].append(_note('discounted:new', title='Новое'))
        self._dispatch()
        self.assertEqual([p['title'] for p in self._payloads()], ['Новое'])

    def test_same_phone_moves_to_the_new_user_after_relogin(self):
        other = User.objects.create_user('roma', password='x')
        client = Client()
        client.force_login(other)

        client.post('/api/push/subscribe/', {
            'endpoint': self.device.endpoint, 'keys': {'p256dh': 'k', 'auth': 'a'},
        }, content_type='application/json')

        self.assertEqual(PushSubscription.objects.get(endpoint=self.device.endpoint).user, other)

    def test_removed_app_drops_its_subscription(self):
        self.items['discounted'] = [_note('discounted:delist:p1')]
        gone = WebPushException('Gone', response=MagicMock(status_code=410))

        with patch('api.notifications.push.webpush', side_effect=gone):
            self._dispatch()

        self.assertFalse(PushSubscription.objects.exists())
        self.assertFalse(PushDelivery.objects.exists())

    def test_unsubscribe_touches_only_own_device(self):
        other = User.objects.create_user('roma', password='x')
        client = Client()
        client.force_login(other)

        client.post('/api/push/unsubscribe/', {'endpoint': self.device.endpoint}, content_type='application/json')

        self.assertTrue(PushSubscription.objects.filter(pk=self.device.pk).exists())

    def test_reopening_the_app_does_not_swallow_a_new_notification(self):
        client = Client()
        client.force_login(self.user)
        self.items['discounted'] = [_note('discounted:new', title='Новое')]

        client.post('/api/push/subscribe/', {
            'endpoint': self.device.endpoint, 'keys': {'p256dh': 'key', 'auth': 'auth'},
        }, content_type='application/json')
        self._dispatch()

        self.assertEqual([p['title'] for p in self._payloads()], ['Новое'])

    def test_foreign_endpoint_is_rejected(self):
        client = Client()
        client.force_login(self.user)

        response = client.post('/api/push/subscribe/', {
            'endpoint': 'https://internal.host/admin', 'keys': {'p256dh': 'k', 'auth': 'a'},
        }, content_type='application/json')

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PushSubscription.objects.filter(endpoint='https://internal.host/admin').exists())

    def test_rejected_by_push_service_drops_subscription(self):
        self.items['discounted'] = [_note('discounted:delist:p1')]
        rejected = WebPushException('Forbidden', response=MagicMock(status_code=403))

        with patch('api.notifications.push.webpush', side_effect=rejected):
            self._dispatch()

        self.assertFalse(PushSubscription.objects.exists())

    def test_network_error_does_not_stop_the_round(self):
        other = User.objects.create_user('roma', password='x')
        UserPageAccess.objects.create(user=other, page_key='discounted')
        PushSubscription.objects.create(user=other, endpoint='https://fcm.googleapis.com/fcm/send/roma', p256dh='k', auth='a')
        self.items['discounted'] = [_note('discounted:delist:p1')]

        def flaky(**kw):
            if kw['subscription_info']['endpoint'].endswith('ivan'):
                raise ConnectionError('сеть')
            self.sent.append(kw)

        with patch('api.notifications.push.webpush', side_effect=flaky):
            stats = self._dispatch()

        self.assertEqual(stats, {'users': 2, 'pushed': 1, 'failed': 1})

    def test_incomplete_subscription_is_rejected(self):
        client = Client()
        client.force_login(self.user)

        response = client.post('/api/push/subscribe/', {'endpoint': 'https://fcm.googleapis.com/fcm/send/x'}, content_type='application/json')

        self.assertEqual(response.status_code, 400)


class TestPushTest(TestCase):
    def test_sends_to_every_own_device(self):
        user = User.objects.create_user('sesen', password='x')
        for n in range(2):
            PushSubscription.objects.create(user=user, endpoint=f'https://fcm.googleapis.com/fcm/send/{n}', p256dh='k', auth='a')
        client = Client()
        client.force_login(user)

        with patch('api.notifications.push.webpush') as sender:
            response = client.post('/api/push/test/')

        self.assertEqual(response.json(), {'sent': 2, 'devices': 2})
        self.assertEqual(json.loads(sender.call_args.kwargs['data'])['title'], 'Тестовое уведомление')
