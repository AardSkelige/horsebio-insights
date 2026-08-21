"""Аналитика использования не должна ломаться от переименования пунктов меню.

Имя страницы пишется в лог строкой на момент визита, поэтому после
переименования пункта одна и та же страница раньше разъезжалась на два
названия, а бейдж, который искался по этой строке, молча переставал
выдаваться. Ключ везде — маршрут.
"""
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from api.access import label_for_route
from api.auth import _compute_badge, _top_pages
from api.models import UserPageEvent


class LabelForRouteTest(TestCase):
    def test_returns_current_label(self):
        self.assertEqual(label_for_route('/inventory'), 'Инвентаризация')
        self.assertEqual(label_for_route('/shipments/products'), 'Товары в отгрузках')

    def test_unknown_route_has_no_label(self):
        self.assertIsNone(label_for_route('/profile'))


class TopPagesTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('lera', password='secret')

    def _visit(self, path, name, seconds=30):
        UserPageEvent.objects.create(
            user=self.user, page_path=path, page_name=name,
            duration_seconds=seconds, created_at=timezone.now(),
        )

    def test_history_survives_a_rename(self):
        """Три визита на /inventory под двумя именами — одна строка, а не две."""
        self._visit('/inventory', 'Мониторинг')
        self._visit('/inventory', 'Мониторинг')
        self._visit('/inventory', 'Инвентаризация')

        rows = _top_pages(UserPageEvent.objects.filter(user=self.user))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['visits'], 3)
        # показываем актуальное название, а не то, что было записано первым
        self.assertEqual(rows[0]['page_name'], 'Инвентаризация')

    def test_page_outside_the_registry_keeps_its_stored_name(self):
        self._visit('/profile', 'Профиль')

        rows = _top_pages(UserPageEvent.objects.filter(user=self.user))

        self.assertEqual(rows[0]['page_name'], 'Профиль')

    def test_extra_annotation_is_passed_through(self):
        self._visit('/inventory', 'Инвентаризация')
        from django.db.models import Count

        rows = _top_pages(
            UserPageEvent.objects.filter(user=self.user),
            {'unique_users': Count('user', distinct=True)},
        )

        self.assertEqual(rows[0]['unique_users'], 1)


class BadgeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sergey', password='secret')

    def _visit(self, path, name):
        UserPageEvent.objects.create(
            user=self.user, page_path=path, page_name=name,
            duration_seconds=60, created_at=timezone.now(),
        )

    def _badge(self):
        return _compute_badge(self.user, UserPageEvent.objects.filter(user=self.user), 1)

    def test_badge_survives_a_rename(self):
        """Страница переименована, бейдж прежний — ищем по маршруту."""
        self._visit('/inventory', 'Инвентаризация')
        self.assertEqual(self._badge()['title'], 'Складской детектив')

    def test_badge_matches_old_stored_name_too(self):
        """Старые записи в логе лежат под прежним именем — бейдж всё равно найдётся."""
        self._visit('/inventory', 'Мониторинг')
        self.assertEqual(self._badge()['title'], 'Складской детектив')

    def test_renamed_production_page_still_has_its_badge(self):
        self._visit('/production/calculator', 'Калькулятор производства')
        self.assertEqual(self._badge()['title'], 'Инженер-рационализатор')

    def test_both_material_pages_share_a_badge(self):
        self._visit('/supplies/materials', 'Материалы в приёмках')
        self.assertEqual(self._badge()['title'], 'Материальный мир')

    def test_unknown_page_falls_back_to_the_default(self):
        self._visit('/profile', 'Профиль')
        self.assertEqual(self._badge()['title'], 'Цифровой бродяга')

    def test_every_badge_route_still_exists_in_the_registry(self):
        """Бейджи привязаны к маршрутам — маршрут не должен исчезнуть незаметно."""
        from api.access import PAGES

        self._visit('/analysis/abc', 'ABC Анализ')
        routes = {p['route'] for p in PAGES}
        # маршруты бейджей достаём из самого словаря внутри _compute_badge
        import inspect
        source = inspect.getsource(_compute_badge)
        badge_routes = {
            line.split("'")[1]
            for line in source.splitlines()
            if line.strip().startswith("'/")
        }
        self.assertTrue(badge_routes)
        self.assertEqual(badge_routes - routes, set())
