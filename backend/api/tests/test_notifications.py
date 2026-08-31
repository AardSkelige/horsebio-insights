"""Тесты уведомлений.

Проверяется две вещи. Во-первых, правила раздела «Уценка»: уведомление должно
появляться ровно тогда, когда по регламенту пора что-то делать, и не должно
двоиться, если у одной позиции сходится сразу несколько поводов.

Во-вторых, само ядро: раздел без прав не должен доходить до пользователя,
прочитанное не должно прятать повод навсегда, а упавший провайдер — ронять
колокольчик целиком.
"""
import json
from datetime import date, timedelta

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase

from api import notifications
from api.models import NotificationState, UserPageAccess
from api.notifications import core
from api.views.discounted import STATE_DELIST, STATE_EXPIRED, STATE_NO_DATE, STATE_OK


def _position(**kwargs):
    """Позиция склада «Уценка» в том виде, в каком её отдаёт positions_snapshot."""
    base = {
        'id': 'p1',
        'article': '06-04GP1600-UC',
        'name': 'Уценка // Пробиотик GastroPro для лошадей, 1600г',
        'state': STATE_OK,
        'expires': (date.today() + timedelta(days=123)).isoformat(),
        'days_left': 123,
        'quantity': 32,
        'published': True,
        'site_price': 1456,
        'site_quantity': 32,
        'ms_url': 'https://online.moysklad.ru/app/#good/edit?id=ui-p1',
        'site_url': 'https://horse-bio.ru/ucenka-probiotik-1600g',
    }
    base.update(kwargs)
    return base


class RulesTest(TestCase):
    """Три повода из регламента — и тишина, когда всё в порядке."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _run(self, positions):
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            return list(notifications.discounted.discounted_notifications())

    def test_silent_when_everything_matches(self):
        self.assertEqual(self._run([_position()]), [])

    def test_delist_when_less_than_two_months_left(self):
        item, = self._run([_position(state=STATE_DELIST, days_left=45)])
        self.assertEqual(item.level, core.CRITICAL)
        self.assertIn('пора снимать с продажи', item.title)
        self.assertIn('45 дн', item.body)
        self.assertIn('Файл для сайта', item.action)
        self.assertEqual(item.key, 'discounted:delist:p1')

    def test_expired_says_how_long_ago(self):
        item, = self._run([_position(state=STATE_EXPIRED, days_left=-8)])
        self.assertEqual(item.level, core.CRITICAL)
        self.assertIn('вышел 8 дн назад', item.body)

    def test_delist_without_a_card_on_the_site_asks_to_write_off(self):
        """Файл не поможет там, где карточки на витрине нет — остаётся списание."""
        item, = self._run([_position(state=STATE_DELIST, days_left=10, published=False,
                                     site_quantity=None)])
        self.assertIn('спишите', item.action)
        self.assertNotIn('Файл для сайта', item.action)

    def test_stock_drift_when_the_site_shows_more_than_we_have(self):
        item, = self._run([_position(quantity=8, site_quantity=12)])
        self.assertEqual(item.level, core.WARNING)
        self.assertIn('остаток на сайте разошёлся', item.title)
        self.assertIn('На витрине 12 шт, на складе 8', item.body)

    def test_no_drift_when_the_site_shows_less(self):
        """Меньше на витрине, чем на складе, — не повод: продать лишнее нельзя."""
        self.assertEqual(self._run([_position(quantity=8, site_quantity=3)]), [])

    def test_sold_out_while_the_card_is_still_selling(self):
        item, = self._run([_position(quantity=0, site_quantity=4)])
        self.assertEqual(item.key, 'discounted:sold-out:p1')
        self.assertIn('на складе ноль', item.title)
        self.assertIn('на витрине всё ещё 4 шт', item.body)

    def test_sold_out_is_silent_when_the_card_is_not_on_the_site(self):
        self.assertEqual(self._run([_position(quantity=0, published=False, site_quantity=None)]), [])

    def test_missing_expiry_date_is_informational_before_publication(self):
        """Товар на складе есть, даты нет — это ожидание шага 6, а не проблема."""
        item, = self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None,
                                     published=False, site_quantity=None)])
        self.assertEqual(item.level, core.INFO)
        self.assertEqual(item.key, 'discounted:no-date:p1')
        self.assertIn('не проставлен «Годен до»', item.title)
        self.assertIn('Леру', item.action)

    def test_missing_expiry_date_on_a_selling_card_is_a_warning(self):
        """Карточка продаётся, а до какого числа можно — неизвестно."""
        item, = self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None)])
        self.assertEqual(item.level, core.WARNING)
        self.assertIn('непонятно, когда снимать', item.body)

    def test_no_date_is_silent_without_stock(self):
        """Карточка заведена, техоперации ещё не было — торопить некого."""
        self.assertEqual(self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None,
                                              quantity=0, published=False,
                                              site_quantity=None)]), [])

    def test_no_date_comes_along_with_a_stock_drift(self):
        """Два дела к двум людям: остаток правит файлом Сергей, дату ставит Лера."""
        items = self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None,
                                     quantity=8, site_quantity=12)])
        self.assertEqual(
            sorted(item.key for item in items),
            ['discounted:no-date:p1', 'discounted:stock:p1'],
        )

    def test_quantity_does_not_change_the_no_date_fingerprint(self):
        first, = self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None,
                                      quantity=8, site_quantity=8)])
        cache.clear()
        second, = self._run([_position(state=STATE_NO_DATE, expires=None, days_left=None,
                                       quantity=6, site_quantity=6)])
        self.assertEqual(first.fingerprint, second.fingerprint)

    def test_one_position_gives_one_notification(self):
        """Пора снимать и остаток разошёлся — действие одно, значит и повод один."""
        items = self._run([_position(state=STATE_DELIST, days_left=30, quantity=8, site_quantity=12)])
        self.assertEqual([item.key for item in items], ['discounted:delist:p1'])

    def test_the_section_name_is_stripped_from_the_title(self):
        item, = self._run([_position(state=STATE_DELIST, days_left=30)])
        self.assertTrue(item.title.startswith('Пробиотик'), item.title)

    def test_days_left_do_not_change_the_fingerprint(self):
        """Иначе приглушение слетало бы каждую ночь само собой."""
        first, = self._run([_position(state=STATE_DELIST, days_left=45)])
        cache.clear()
        second, = self._run([_position(state=STATE_DELIST, days_left=44)])
        self.assertEqual(first.fingerprint, second.fingerprint)


class CoreTest(TestCase):
    """Ядро: права, кеш, отметки, изоляция упавшего провайдера."""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=self.user, page_key='discounted')

    def tearDown(self):
        cache.clear()

    def _collect(self, positions, **kwargs):
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            return notifications.collect(self.user, **kwargs)

    def test_counts_by_level_and_source(self):
        data = self._collect([
            _position(id='p1', state=STATE_DELIST, days_left=30),
            _position(id='p2', quantity=8, site_quantity=12),
        ])
        self.assertEqual(data['counts']['total'], 2)
        self.assertEqual(data['counts']['unseen'], 2)
        self.assertEqual(data['counts']['critical'], 1)
        self.assertEqual(data['by_source']['discounted']['total'], 2)
        # Раздел подсвечивается по самому серьёзному своему уведомлению
        self.assertEqual(data['by_source']['discounted']['level'], core.CRITICAL)

    def test_the_section_carries_its_label_and_route_from_the_registry(self):
        data = self._collect([_position(state=STATE_DELIST, days_left=30)])
        item = data['items'][0]
        self.assertEqual(item['source_label'], 'Уценка')
        self.assertEqual(item['route'], '/discounted')

    def test_a_user_without_access_to_the_section_sees_nothing(self):
        UserPageAccess.objects.filter(user=self.user).delete()
        data = self._collect([_position(state=STATE_DELIST, days_left=30)])
        self.assertEqual(data['items'], [])

    def test_a_broken_provider_does_not_break_the_rest(self):
        def boom():
            raise RuntimeError('МойСклад не ответил')

        core._PROVIDERS['broken'] = boom
        self.addCleanup(core._PROVIDERS.pop, 'broken', None)
        UserPageAccess.objects.create(user=self.user, page_key='broken')

        data = self._collect([_position(state=STATE_DELIST, days_left=30)])
        self.assertEqual(data['counts']['total'], 1)

    def test_reading_clears_the_unread_counter_but_keeps_the_notification(self):
        """Прочитанное не исчезает: дело осталось, просто человек о нём знает."""
        positions = [_position(state=STATE_DELIST, days_left=30)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, [])
            data = notifications.collect(self.user)
        self.assertEqual(data['counts']['unseen'], 0)
        self.assertEqual(data['counts']['total'], 1)
        self.assertTrue(data['items'][0]['seen'])

    def test_a_changed_fingerprint_makes_it_unread_again(self):
        """Прочитанное не прячет проблему: изменились цифры — уведомление новое."""
        with patch('api.notifications.discounted.positions_snapshot',
                   return_value=[_position(quantity=8, site_quantity=12)]):
            notifications.mark_read(self.user, ['discounted:stock:p1'])
        cache.clear()

        data = self._collect([_position(quantity=8, site_quantity=20)])
        self.assertFalse(data['items'][0]['seen'])
        self.assertEqual(data['counts']['unseen'], 1)

    def test_the_same_notification_stays_read(self):
        """Пересчёт по тем же данным не делает уведомление новым снова."""
        positions = [_position(quantity=8, site_quantity=12)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, [])
        cache.clear()

        data = self._collect([_position(quantity=8, site_quantity=12)])
        self.assertTrue(data['items'][0]['seen'])

    def test_a_key_given_as_a_string_still_marks(self):
        """Интерфейс мог прислать один ключ строкой — молча ничего не делать нельзя."""
        positions = [_position(state=STATE_DELIST, days_left=30)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            marked = notifications.mark_read(self.user, 'discounted:delist:p1')
            data = notifications.collect(self.user)
        self.assertEqual(marked, ['discounted:delist:p1'])
        self.assertEqual(data['counts']['unseen'], 0)

    def test_a_recurring_notification_comes_back_unread(self):
        """Повод закрылся и возник снова — уведомление снова новое.

        Отпечаток у «раскуплено» один и тот же, поэтому отметку надо снимать
        вместе с самим поводом, иначе колокольчик промолчит навсегда.
        """
        sold_out = [_position(quantity=0, site_quantity=4)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=sold_out):
            notifications.mark_read(self.user, [])
        cache.clear()

        # Товар довезли — повода нет, отметка должна уйти вместе с ним
        self._collect([_position(quantity=10, site_quantity=10)])
        self.assertEqual(NotificationState.objects.filter(user=self.user).count(), 0)
        cache.clear()

        data = self._collect(sold_out)
        self.assertEqual(data['counts']['unseen'], 1)
        self.assertFalse(data['items'][0]['seen'])

    def test_a_failed_section_does_not_wipe_read_marks(self):
        """Раздел не ответил — его поводы могли остаться, отметку стирать нельзя."""
        positions = [_position(state=STATE_DELIST, days_left=30)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, [])
        cache.clear()

        def boom():
            raise RuntimeError('МойСклад не ответил')

        core._PROVIDERS['discounted'], original = boom, core._PROVIDERS['discounted']
        self.addCleanup(core._PROVIDERS.__setitem__, 'discounted', original)

        notifications.collect(self.user)
        self.assertEqual(NotificationState.objects.filter(user=self.user).count(), 1)

    def test_badge_level_counts_only_unread(self):
        """Прочитанное критическое не должно красить точку в красный."""
        positions = [
            _position(id='p1', state=STATE_DELIST, days_left=30),          # critical
            _position(id='p2', state=STATE_NO_DATE, expires=None, days_left=None,
                      published=False, site_quantity=None),                # info
        ]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, ['discounted:delist:p1'])
            data = notifications.collect(self.user)

        self.assertEqual(data['counts']['level'], core.INFO)
        self.assertEqual(data['by_source']['discounted']['level'], core.INFO)
        # счётчики по уровням по-прежнему описывают весь список
        self.assertEqual(data['counts']['critical'], 1)

    def test_badge_level_is_empty_when_everything_is_read(self):
        positions = [_position(state=STATE_DELIST, days_left=30)]
        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, [])
            data = notifications.collect(self.user)
        self.assertIsNone(data['counts']['level'])
        self.assertIsNone(data['by_source']['discounted']['level'])

    def test_an_unknown_level_does_not_break_the_bell(self):
        """Опечатка в провайдере не должна ронять колокольчик для всех."""
        def odd():
            yield core.Notification(key='odd:1', level='warn', title='Опечатка в уровне')

        core._PROVIDERS['odd'] = odd
        self.addCleanup(core._PROVIDERS.pop, 'odd', None)
        UserPageAccess.objects.create(user=self.user, page_key='odd')

        data = self._collect([_position()])
        self.assertEqual(data['counts']['total'], 1)
        self.assertEqual(data['items'][0]['key'], 'odd:1')

    def test_state_is_personal(self):
        other = User.objects.create_user('lera', password='secret')
        UserPageAccess.objects.create(user=other, page_key='discounted')
        positions = [_position(state=STATE_DELIST, days_left=30)]

        with patch('api.notifications.discounted.positions_snapshot', return_value=positions):
            notifications.mark_read(self.user, [])
            data = notifications.collect(other)
        self.assertEqual(data['counts']['unseen'], 1)

    def test_provider_result_is_cached(self):
        """Колокольчик опрашивается из любого раздела — ходить в МойСклад каждый раз нельзя."""
        with patch('api.notifications.discounted.positions_snapshot',
                   return_value=[_position()]) as snapshot:
            notifications.collect(self.user)
            notifications.collect(self.user)
        self.assertEqual(snapshot.call_count, 1)

    def test_refresh_bypasses_the_cache(self):
        with patch('api.notifications.discounted.positions_snapshot',
                   return_value=[_position()]) as snapshot:
            notifications.collect(self.user)
            notifications.collect(self.user, refresh=True)
        self.assertEqual(snapshot.call_count, 2)


class EndpointTest(TestCase):
    """Эндпоинты колокольчика."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        user = User.objects.create_user('sergey', password='secret')
        UserPageAccess.objects.create(user=user, page_key='discounted')
        self.client.login(username='sergey', password='secret')
        self.user = user

    def tearDown(self):
        cache.clear()

    def _patched(self, positions=None):
        return patch('api.notifications.discounted.positions_snapshot',
                     return_value=positions if positions is not None
                     else [_position(state=STATE_DELIST, days_left=30)])

    def test_list_returns_items_and_counts(self):
        with self._patched():
            response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['counts']['unseen'], 1)

    def test_anonymous_is_not_allowed(self):
        self.client.logout()
        response = self.client.get('/api/notifications/')
        self.assertIn(response.status_code, (302, 401, 403))

    def test_read_without_keys_marks_everything(self):
        with self._patched():
            response = self.client.post('/api/notifications/read/', data='{}',
                                        content_type='application/json')
        # Ответ уже содержит пересчитанный список — второй запрос не нужен
        self.assertEqual(response.json()['counts']['unseen'], 0)
        self.assertEqual(response.json()['counts']['total'], 1)
        self.assertEqual(NotificationState.objects.filter(user=self.user).count(), 1)

    def test_read_can_be_undone(self):
        """Отметку человек снимает так же, как ставит."""
        with self._patched():
            self.client.post('/api/notifications/read/', data='{}',
                             content_type='application/json')
            response = self.client.post(
                '/api/notifications/read/',
                data=json.dumps({'keys': ['discounted:delist:p1'], 'read': False}),
                content_type='application/json',
            )
        self.assertEqual(response.json()['counts']['unseen'], 1)
        self.assertFalse(response.json()['items'][0]['seen'])

    def test_read_by_key_touches_only_that_one(self):
        positions = [
            _position(id='p1', state=STATE_DELIST, days_left=30),
            _position(id='p2', quantity=8, site_quantity=12),
        ]
        with self._patched(positions):
            self.client.post('/api/notifications/read/',
                             data=json.dumps({'keys': ['discounted:delist:p1']}),
                             content_type='application/json')
            data = self.client.get('/api/notifications/').json()
        by_key = {item['key']: item['seen'] for item in data['items']}
        self.assertTrue(by_key['discounted:delist:p1'])
        self.assertFalse(by_key['discounted:stock:p2'])
