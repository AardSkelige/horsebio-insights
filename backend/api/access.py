"""
Постраничный контроль доступа.

Единый реестр страниц приложения (PAGES) — источник правды и для серверной
защиты (middleware), и для админ-UI «Доступы». Каждая страница объявляет:
  key           — стабильный идентификатор (совпадает с фронтовым page-key);
  label / group — для отображения в UI управления доступом;
  route         — фронтовый путь (справочно);
  api_prefixes  — префиксы API, «принадлежащие» странице.

Правило доступа (enforce_page_access в middleware):
  • путь, занятый одной или несколькими страницами, доступен, только если у
    пользователя есть хотя бы одна из этих страниц;
  • путь, не занятый ни одной страницей (общие: auth, stats, latest), —
    доступен любому аутентифицированному пользователю;
  • суперпользователь имеет доступ ко всему.
"""

# superuser=True — страница только для суперпользователя (в UI доступов не выдаётся).
PAGES = [
    {'key': 'shipments-products',       'label': 'Товары',          'group': 'Отгрузки',        'route': '/shipments/products',       'api_prefixes': ['/api/products/', '/api/shipments/']},
    {'key': 'shipments-counterparties', 'label': 'Покупатели',      'group': 'Отгрузки',        'route': '/shipments/counterparties', 'api_prefixes': ['/api/counterparties/']},
    {'key': 'shipments-materials',      'label': 'Материалы',       'group': 'Отгрузки',        'route': '/shipments/materials',      'api_prefixes': ['/api/materials/']},
    {'key': 'deadlines',                'label': 'Сроки оплаты',    'group': 'Отгрузки',        'route': '/deadlines',                'api_prefixes': ['/api/deadlines/']},
    {'key': 'site-orders',              'label': 'Заказы сайта',    'group': 'Заказы сайта',    'route': '/site-orders',              'api_prefixes': ['/api/site-orders/']},
    {'key': 'supplies-materials',       'label': 'Приёмки',         'group': 'Приёмки',         'route': '/supplies/materials',       'api_prefixes': ['/api/supplies/materials/', '/api/supplies/']},
    {'key': 'supplies-suppliers',       'label': 'Поставщики',      'group': 'Приёмки',         'route': '/supplies/suppliers',       'api_prefixes': ['/api/supplies/suppliers/']},
    {'key': 'production',               'label': 'Производство',    'group': 'Производство',    'route': '/production/calculator',    'api_prefixes': ['/api/production/']},
    {'key': 'inventory',                'label': 'Инвентаризация',  'group': 'Инвентаризация',  'route': '/inventory',                'api_prefixes': ['/api/inventory/']},
    {'key': 'abc',                      'label': 'ABC Анализ',      'group': 'Аналитика',       'route': '/analysis/abc',             'api_prefixes': ['/api/analysis/abc/']},
    {'key': 'seasonal',                 'label': 'Сезонность',      'group': 'Аналитика',       'route': '/analysis/seasonal',        'api_prefixes': ['/api/analysis/seasonal/']},
    {'key': 'fbo',                      'label': 'FBO Заказы',      'group': 'Аналитика',       'route': '/analysis/fbo',             'api_prefixes': ['/api/analysis/fbo/']},
    {'key': 'counterparty-groups',      'label': 'Группы клиентов', 'group': 'Аналитика',       'route': '/analysis/counterparty-groups', 'api_prefixes': ['/api/counterparty-groups/']},
    {'key': 'purchases',                'label': 'Помощник закупок','group': 'Аналитика',       'route': '/purchases/analysis',       'api_prefixes': ['/api/analysis/purchase/']},
    {'key': 'ozon-fbo-converter',       'label': 'FBO Конвертер',   'group': 'Аналитика',       'route': '/ozon/fbo-converter',       'api_prefixes': ['/api/ozon/fbo-converter/']},
    {'key': 'ozon',                     'label': 'Ozon',            'group': 'Аналитика',       'route': '/analysis/ozon',            'api_prefixes': ['/api/ozon/']},
    {'key': 'cash-flow',                'label': 'ДДС',             'group': 'Аналитика',       'route': '/analysis/cash-flow',       'api_prefixes': ['/api/analysis/cash-flow/']},
    {'key': 'cash-flow-v2',             'label': 'ДДС · новая',     'group': 'Аналитика',       'route': '/analysis/cash-flow-v2',    'api_prefixes': ['/api/analysis/cash-flow/']},
    # Только для суперпользователя — в UI доступов не показываются
    {'key': 'checks',           'label': 'Проверки',          'group': 'Администрирование', 'route': '/checks',           'api_prefixes': ['/api/checks/'], 'superuser': True},
    {'key': 'system-analytics', 'label': 'Аналитика системы', 'group': 'Администрирование', 'route': '/system/analytics', 'api_prefixes': ['/api/auth/admin-analytics/', '/api/auth/sessions/'], 'superuser': True},
]

# Ozon-конвертер и Ozon-аналитика делят общий префикс /api/ozon/. Чтобы доступ к
# конвертеру не открывал всю Ozon-аналитику, более специфичный префикс проверяем
# первым — правило ниже сортирует префиксы по длине (длинный = специфичнее).

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
    Общие пути (не принадлежащие ни одной странице) — разрешены всем.
    """
    if user.is_authenticated and user.is_superuser:
        return True
    owners = page_keys_for_path(path)
    if not owners:
        return True  # общий эндпоинт
    return bool(owners & user_allowed_page_keys(user))
