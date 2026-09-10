"""
Каждый путь приложения обязан иметь решение о правах.

Тест не проверяет, что права расставлены правильно — это решает человек.
Он проверяет, что решение принято вообще: маршрут принадлежит странице,
назван общим, назван суперюзерским или объявлен публичным. Маршрут, о котором
не сказано ничего, роняет сборку с собственным именем.

Так закрыто место, из-за которого 10.09.2026 тридцать семь путей оказались
открыты любому залогиненному: никто их не открывал — просто забыли приписать
к странице, а умолчание пускало.
"""
from django.test import TestCase
from django.urls import get_resolver

from api.access import PAGES, COMMON_PREFIXES, SUPERUSER_PREFIXES, page_keys_for_path
from api.middleware import APIAuthenticationMiddleware


def _all_routes():
    """Пути всех маршрутов проекта, как их видит middleware — с ведущим слешем."""
    def walk(patterns, prefix=''):
        for entry in patterns:
            if hasattr(entry, 'url_patterns'):
                yield from walk(entry.url_patterns, prefix + str(entry.pattern))
            else:
                yield prefix + str(entry.pattern)

    return sorted({'/' + route for route in walk(get_resolver().url_patterns)})


def _guarded_routes():
    """Маршруты, которые проходят через постраничную проверку прав."""
    return [
        route for route in _all_routes()
        if route.startswith('/api/') or route.startswith('/parser/')
    ]


class AccessCoverageTests(TestCase):
    def test_every_route_has_a_decision(self):
        """Незакрытый маршрут — это открытая ручка, и молчать о ней нельзя."""
        public = tuple(APIAuthenticationMiddleware.PUBLIC_PATHS)
        outside = tuple(COMMON_PREFIXES) + tuple(SUPERUSER_PREFIXES)

        undecided = [
            route for route in _guarded_routes()
            if not page_keys_for_path(route)
            and not route.startswith(outside)
            and not route.startswith(public)
        ]

        self.assertEqual(undecided, [], (
            'Эти маршруты не отнесены ни к странице, ни к общим, ни к суперюзерским, '
            'ни к публичным — и потому закрыты для всех, кроме суперпользователя. '
            'Решение принимается в api/access.py: добавить префикс странице '
            '(api_prefixes), в COMMON_PREFIXES или в SUPERUSER_PREFIXES.'
        ))

    def test_every_page_prefix_has_routes(self):
        """Префикс без маршрутов — след переименованной ручки: правило есть,
        а защищать ему нечего, и настоящий путь остаётся без владельца."""
        routes = _guarded_routes()
        orphaned = [
            (page['key'], prefix)
            for page in PAGES
            for prefix in page['api_prefixes']
            if not any(route.startswith(prefix) for route in routes)
        ]

        self.assertEqual(orphaned, [], 'Префиксы страниц, под которыми нет ни одного маршрута')

    def test_prefixes_outside_pages_have_routes(self):
        """То же самое для общих и суперюзерских списков."""
        routes = _guarded_routes()
        orphaned = [
            prefix for prefix in COMMON_PREFIXES + SUPERUSER_PREFIXES
            if not any(route.startswith(prefix) for route in routes)
        ]

        self.assertEqual(orphaned, [], 'Префиксы вне страниц, под которыми нет ни одного маршрута')
