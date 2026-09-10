"""
Постраничный контроль доступа.

Единый реестр страниц приложения (PAGES) — источник правды и для серверной
защиты (middleware), и для админ-UI «Доступы». Каждая страница объявляет:
  key           — стабильный идентификатор (совпадает с фронтовым page-key);
  label / group — для отображения в UI управления доступом;
  route         — фронтовый путь (справочно);
  api_prefixes  — префиксы API, «принадлежащие» странице.

Правило доступа (user_can_access_path, зовётся из middleware):
  • суперпользователь имеет доступ ко всему;
  • путь, занятый одной или несколькими страницами, доступен, только если
    у пользователя есть хотя бы одна из этих страниц;
  • путь из COMMON_PREFIXES — любому аутентифицированному;
  • всё остальное — запрещено.

Последнее правило перевёрнуто 10.09.2026. До этого путь без владельца был
открыт любому залогиненному, и забытый префикс означал открытую ручку —
её защищала только память автора вьюхи. Теперь забывчивость закрывает:
новый путь недоступен никому, кроме суперпользователя, пока его не отнесли
к странице или к общим. Чтобы это не выяснялось на проде, состав проверяет
тест api/tests/test_access_coverage.py — он падает с именем маршрута.
"""

# superuser=True — страница только для суперпользователя (в UI доступов не выдаётся).
PAGES = [
    # Порядок и подписи держим синхронными с меню (frontend/src/components/layout/
    # sidebar/navGroups.js): страница «Доступы» показывает те же группы, что видит
    # пользователь в сайдбаре, иначе деление разъезжается.
    {'key': 'shipments-products',       'label': 'Товары в отгрузках',       'group': 'МойСклад',          'route': '/shipments/products',          'api_prefixes': ['/api/products/', '/api/shipments/']},
    {'key': 'shipments-counterparties', 'label': 'Покупатели',               'group': 'МойСклад',          'route': '/shipments/counterparties',    'api_prefixes': ['/api/counterparties/']},
    {'key': 'shipments-materials',      'label': 'Материалы в отгрузках',    'group': 'МойСклад',          'route': '/shipments/materials',         'api_prefixes': ['/api/materials/']},
    {'key': 'deadlines',                'label': 'Сроки оплаты',             'group': 'МойСклад',          'route': '/deadlines',                   'api_prefixes': ['/api/deadlines/']},
    {'key': 'supplies-materials',       'label': 'Материалы в приёмках',     'group': 'МойСклад',          'route': '/supplies/materials',          'api_prefixes': ['/api/supplies/materials/', '/api/supplies/']},
    {'key': 'supplies-suppliers',       'label': 'Поставщики',               'group': 'МойСклад',          'route': '/supplies/suppliers',          'api_prefixes': ['/api/supplies/suppliers/']},
    {'key': 'production',               'label': 'Расчёт производства', 'group': 'МойСклад',          'route': '/production/calculator',       'api_prefixes': ['/api/production/']},
    {'key': 'inventory',                'label': 'Инвентаризация',           'group': 'МойСклад',          'route': '/inventory',                   'api_prefixes': ['/api/inventory/']},

    {'key': 'site-orders',              'label': 'Заказы сайта',             'group': 'Сайт',              'route': '/site-orders',                 'api_prefixes': ['/api/site-orders/']},
    {'key': 'discounted',               'label': 'Уценка',                   'group': 'Сайт',              'route': '/discounted',                  'api_prefixes': ['/api/discounted/']},
    {'key': 'delivery-calc',            'label': 'Расчёт доставки',          'group': 'Сайт',              'route': '/delivery/calculator',         'api_prefixes': ['/api/delivery/']},

    {'key': 'abc',                      'label': 'ABC Анализ',               'group': 'Аналитика',         'route': '/analysis/abc',                'api_prefixes': ['/api/analysis/abc/']},
    {'key': 'seasonal',                 'label': 'Сезонность',               'group': 'Аналитика',         'route': '/analysis/seasonal',           'api_prefixes': ['/api/analysis/seasonal/']},
    {'key': 'fbo',                      'label': 'FBO Заказы',               'group': 'Аналитика',         'route': '/analysis/fbo',                'api_prefixes': ['/api/analysis/fbo/']},
    {'key': 'fbo-stock',                'label': 'Остатки для FBO',          'group': 'Аналитика',         'route': '/analysis/fbo-stock',          'api_prefixes': ['/api/analysis/fbo-stock/']},
    {'key': 'counterparty-groups',      'label': 'Группы клиентов',          'group': 'Аналитика',         'route': '/analysis/counterparty-groups','api_prefixes': ['/api/counterparty-groups/']},
    {'key': 'purchases',                'label': 'Помощник закупок',         'group': 'Аналитика',         'route': '/purchases/analysis',          'api_prefixes': ['/api/analysis/purchase/']},
    {'key': 'ozon-fbo-converter',       'label': 'FBO Конвертер',            'group': 'Аналитика',         'route': '/ozon/fbo-converter',          'api_prefixes': ['/api/ozon/fbo-converter/']},
    {'key': 'ozon',                     'label': 'Ozon',                     'group': 'Аналитика',         'route': '/analysis/ozon',               'api_prefixes': ['/api/ozon/']},
    {'key': 'cash-flow',                'label': 'ДДС',                      'group': 'Аналитика',         'route': '/analysis/cash-flow',          'api_prefixes': ['/api/analysis/cash-flow/']},
    {'key': 'cash-flow-v2',             'label': 'ДДС · новая',              'group': 'Аналитика',         'route': '/analysis/cash-flow-v2',       'api_prefixes': ['/api/analysis/cash-flow/']},

    # Только для суперпользователя — в UI доступов не показываются
    {'key': 'checks',                   'label': 'Проверки',                 'group': 'Администрирование', 'route': '/checks',                      'api_prefixes': ['/api/checks/'], 'superuser': True},
    {'key': 'system-analytics',         'label': 'Аналитика системы',        'group': 'Администрирование', 'route': '/system/analytics',            'api_prefixes': ['/api/auth/admin-analytics/', '/api/auth/sessions/'], 'superuser': True},
]

# Ozon-конвертер и Ozon-аналитика делят общий префикс /api/ozon/. Чтобы доступ к
# конвертеру не открывал всю Ozon-аналитику, более специфичный префикс проверяем
# первым — правило ниже сортирует префиксы по длине (длинный = специфичнее).

# Пути вне страниц. Раньше такие были открыты всем просто потому, что их забыли
# приписать к странице; теперь каждый назван вслух — и это решение, а не умолчание.

# Доступны любому аутентифицированному: общие для всего приложения.
COMMON_PREFIXES = [
    '/api/auth/',           # сессия, своя активность, настройки главной
    '/api/stats/',          # счётчики на главной
    '/api/latest/',         # отметка свежести данных
    '/api/notifications/',  # колокольчик: сам считает по правам пользователя
]

# Только суперпользователь. Страницы у этих путей нет, поэтому и владельца нет —
# но открытыми они быть не должны.
SUPERUSER_PREFIXES = [
    '/parser/',                  # синхронизация: трогает всю базу и ходит в МойСклад
    '/api/auth/pages-access/',   # управление правами; вьюха проверяет и сама
    '/api/ozon-logistics/',      # диагностика и OAuth Ozon Доставки; корзина сайта
                                 # (/api/ozon-logistics/site/) — в PUBLIC_PATHS,
                                 # сюда она не доходит: там браузер покупателя без сессии
]

# Длинный префикс специфичнее короткого: /api/auth/pages-access/ должен победить
# общий /api/auth/, иначе управление правами окажется доступно всем.
_OUTSIDE_PAGES = sorted(
    [(prefix, 'common') for prefix in COMMON_PREFIXES]
    + [(prefix, 'superuser') for prefix in SUPERUSER_PREFIXES],
    key=lambda pair: len(pair[0]), reverse=True,
)


def path_outside_pages(path):
    """'common', 'superuser' или None — для пути, не принадлежащего странице."""
    for prefix, kind in _OUTSIDE_PAGES:
        if path.startswith(prefix):
            return kind
    return None


_ROUTE_LABELS = {p['route']: p['label'] for p in PAGES}
_PAGES_BY_KEY = {p['key']: p for p in PAGES}


def page_by_key(key):
    """Описание страницы по её ключу.

    Нужно всем, кто хочет назвать раздел так же, как он назван в меню, и увести
    в него по тому же маршруту: уведомления, письма, отчёты. Реестр здесь —
    единственное место, где эта пара живёт.
    """
    return _PAGES_BY_KEY.get(key)


def label_for_route(route):
    """Актуальная подпись страницы по её маршруту.

    Аналитика использования хранит имя страницы строкой на момент визита, поэтому
    после переименования пункта меню история одной и той же страницы разъезжается
    на несколько названий. Ключ у нас — маршрут, он не меняется; имя всегда берём
    отсюда, а сохранённое в логе используем лишь как запасное.
    """
    return _ROUTE_LABELS.get(route)


# Ключи страниц, доступных обычному пользователю (можно выдавать в UI)
ASSIGNABLE_PAGE_KEYS = [p['key'] for p in PAGES if not p.get('superuser')]
_VALID_KEYS = {p['key'] for p in PAGES}

# Плоский список (prefix, {page_keys}) — отсортирован: длинные префиксы раньше
_PREFIX_OWNERS = []
for _p in PAGES:
    for _prefix in _p['api_prefixes']:
        _PREFIX_OWNERS.append((_prefix, _p['key']))
# группируем ключи по префиксу
_PREFIX_MAP = {}
for _prefix, _key in _PREFIX_OWNERS:
    _PREFIX_MAP.setdefault(_prefix, set()).add(_key)
_SORTED_PREFIXES = sorted(_PREFIX_MAP.keys(), key=len, reverse=True)


def page_keys_for_path(path):
    """
    Ключи страниц, «владеющих» данным API-путём (по самому специфичному
    совпавшему префиксу). Пустое множество — путь общий, доступен всем.
    """
    for prefix in _SORTED_PREFIXES:
        if path.startswith(prefix):
            return _PREFIX_MAP[prefix]
    return set()


def sanitize_page_keys(keys):
    """Оставить только валидные, назначаемые (не суперюзерские) ключи страниц."""
    return sorted(k for k in set(keys) if k in _VALID_KEYS and k in ASSIGNABLE_PAGE_KEYS)


def pages_catalog():
    """Каталог назначаемых страниц для админ-UI (без суперюзерских)."""
    return [
        {'key': p['key'], 'label': p['label'], 'group': p['group'], 'route': p['route']}
        for p in PAGES if not p.get('superuser')
    ]


def user_allowed_page_keys(user):
    """
    Набор ключей страниц, разрешённых пользователю.
    Суперпользователь — все страницы (включая суперюзерские).
    """
    if not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(_VALID_KEYS)
    from api.models import UserPageAccess
    return set(
        UserPageAccess.objects.filter(user=user).values_list('page_key', flat=True)
    )


def grant_all_assignable_pages(user):
    """Выдать пользователю все назначаемые страницы (идемпотентно)."""
    from api.models import UserPageAccess
    UserPageAccess.objects.bulk_create(
        [UserPageAccess(user=user, page_key=k) for k in ASSIGNABLE_PAGE_KEYS],
        ignore_conflicts=True,
    )


def user_can_access_path(user, path):
    """
    Разрешён ли пользователю данный API-путь по постраничным правам.

    Путь без владельца разрешён, только если он назван общим (COMMON_PREFIXES).
    Незнакомый путь закрыт: забытая ручка не должна открываться сама.
    """
    if user.is_authenticated and user.is_superuser:
        return True
    owners = page_keys_for_path(path)
    if owners:
        return bool(owners & user_allowed_page_keys(user))
    return path_outside_pages(path) == 'common'
