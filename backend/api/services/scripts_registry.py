# api/services/scripts_registry.py
"""
Реестр скриптов проверок: что запускается, чем и с какими аргументами.

Единственный источник правды о задачах — его читают страница «Проверки»,
монитор скриптов и команда `manage.py run_check`. Лежит в сервисном слое,
а не во view: запуск по расписанию идёт мимо HTTP, и знание о задачах
не должно зависеть от того, поднят ли веб-процесс.

Поле `schedule` — подпись для интерфейса, а не расписание. Настоящее живёт
в crontab сервера (`deploy/cron/horsebio.cron`), и проверять его надо там:
`crontab -l | grep -c horsebio-check.sh`.
"""

# Предохранитель от зависшего процесса, а не инструмент расписания: прогон,
# который не уложился, снимается с кодом 124 (как у timeout(1)) и виден
# в карточке.
#
# Измерено 05.09.2026 на боевом. По CheckRunResult (структурированные
# проверки): возвраты — максимум 4801 с при среднем 135, health_check — 628 с,
# остальные под сотню. У задач без CheckRunResult длительность считана
# по логам (метка запуска в имени файла против времени последней записи):
# синхронизация данных — 169 с, пункты выдачи Ozon — 58 с, инвентаризация —
# 25 с, прочие секунды. То есть получас — запас в десять раз ко всему,
# кроме возвратов, которым предел задан отдельно.
DEFAULT_TIMEOUT_SEC = 1800

SCRIPTS_CONFIG = [
    {
        'id': 'horsebio_health_check',
        'topic': 'Себестоимость',
        'name': 'Health Check',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 08:00',
        'description': 'Комплекс из 13 проверок: FIFO-себестоимость, документы, цены в приёмках, коды товаров, черновики',
        'script': '/app/moysklad/horsebio/02_checks/01_health/scripts/01_health_check.py',
        'args': ['--full'],
        'structured': True,
    },
    {
        'id': 'horsebio_buy_prices',
        'topic': 'Себестоимость',
        'name': 'Закупочные цены',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:50',
        'description': 'Синхронизация buyPrice из FIFO-себестоимости',
        'script': '/app/moysklad/horsebio/01_daemons/02_buy_prices/scripts/01_sync_buy_prices.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_pending_returns',
        'topic': 'Возвраты',
        'name': 'Что разобрать из возвратов',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:45',
        'description': 'Сколько денег висит в возвратах и что требует действия',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/04_pending_returns.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_returns',
        'topic': 'Возвраты',
        'name': 'Все ли возвраты заведены',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:00',
        'description': 'Робот берёт у маркетплейсов список возвратов и заводит документы',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/01_monitor_returns.py',
        'args': [],
        'structured': True,
        # Единственная задача, которой не хватает получаса: маркетплейсы отдают
        # списки возвратов постранично и медленно. Измерено 05.09.2026 —
        # максимум 4801 с из 103 прогонов при среднем 135.
        'timeout': 7200,
    },
    {
        'id': 'horsebio_returns_ozon_enrich',
        'topic': 'Возвраты',
        'name': 'Где едут возвраты Озон',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:15',
        'description': 'Робот спрашивает у Ozon, где коробка, и ставит статус на документ',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/02_enrich_ozon_returns.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_returns_wb_enrich',
        'topic': 'Возвраты',
        'name': 'Где едут возвраты ВБ',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 09:30',
        'description': 'Робот берёт статус из отчёта Wildberries и ставит его на документ',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/03_enrich_wb_returns.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_zero_cost_returns',
        'topic': 'Возвраты',
        'name': 'Нет ли возвратов без себестоимости',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 ч с 10:00',
        'description': 'Проведённые возвраты не занижают FIFO-себестоимость готовой продукции',
        'script': '/app/moysklad/horsebio/01_daemons/03_returns/scripts/05_zero_cost_returns.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_deadlines',
        'topic': 'Оплаты',
        'name': 'Сроки оплаты',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:20',
        'description': 'Мониторинг просроченных и скоро истекающих оплат',
        'script': '/app/moysklad/horsebio/01_daemons/05_payment_deadline/scripts/01_check_deadlines.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_order_email_sync',
        'topic': 'Заказы сайта',
        'name': 'Чтение писем о заказах',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Читает почту info@horse-bio.ru и распознаёт заказы в письмах-уведомлениях с сайта (МойСклад не трогает)',
        'script': '/app/moysklad/horsebio/01_daemons/06_order_email_sync/scripts/01_read_order_emails.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_order_email_create',
        'topic': 'Заказы сайта',
        'name': 'Заведение заказов в МойСклад',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Заводит черновик заказа сразу после письма о заказе, платёж и проведение — после письма об оплате',
        'script': '/app/moysklad/horsebio/01_daemons/06_order_email_sync/scripts/02_create_orders.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_cdek_waybills',
        'topic': 'Заказы сайта',
        'name': 'Накладные СДЭК',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Формирует накладную СДЭК для оплаченных одиночных заказов сайта и прикрепляет PDF к заказу в МойСклад',
        'script': '/app/moysklad/horsebio/01_daemons/07_cdek_waybills/scripts/01_create_waybills.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_site_orders_reconcile',
        'topic': 'Заказы сайта',
        'name': 'Сверка заказов с сайтом',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:40',
        'description': 'Сверяет заказы сайта с МойСклад по выгрузке CommerceML: не потерялся ли оплаченный заказ, сходятся ли сумма и оплата с учётом скидок',
        'script': '/app/moysklad/horsebio/02_checks/02_site_orders/scripts/01_reconcile_site_orders.py',
        'args': [],
        'structured': True,
    },
    {
        'id': 'horsebio_data_sync',
        'topic': 'Обновление данных',
        'name': 'Синхронизация данных',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 11:00',
        'description': 'Автосинхронизация данных МойСклад за последние 7 дней (Django-команда auto_sync_weekly)',
        'script': '/app/manage.py',
        'args': ['auto_sync_weekly'],
    },
    {
        'id': 'horsebio_ozon_products',
        'topic': 'Обновление данных',
        'name': 'Товары Ozon',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:35',
        'description': 'Сопоставление артикулов с sku в Ozon для Ozon Доставки (Django-команда sync_ozon_products)',
        'script': '/app/manage.py',
        'args': ['sync_ozon_products'],
    },
    {
        'id': 'horsebio_ozon_points',
        'topic': 'Обновление данных',
        'name': 'Пункты выдачи Ozon',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:40',
        'description': 'Координаты ~94 тыс. ПВЗ для карты в корзине (Django-команда sync_ozon_pickup_points)',
        'script': '/app/manage.py',
        'args': ['sync_ozon_pickup_points'],
    },
    {
        'id': 'horsebio_ozon_orders',
        'topic': 'Обновление данных',
        'name': 'Заказы Ozon Доставки',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Создание заказов в Ozon по оплаченным заказам сайта (Django-команда create_ozon_orders)',
        'script': '/app/manage.py',
        'args': ['create_ozon_orders'],
    },
    {
        'id': 'horsebio_ozon_postings',
        'topic': 'Обновление данных',
        'name': 'Статусы отправлений Ozon',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Статусы отправлений Ozon Доставки: отмены и невыкупы, по которым надо вернуть деньги (Django-команда sync_ozon_postings)',
        'script': '/app/manage.py',
        'args': ['sync_ozon_postings'],
    },
    {
        'id': 'horsebio_ozon_returns',
        'topic': 'Обновление данных',
        'name': 'Возвраты Ozon Доставки',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Возвраты по нашим отправлениям Ozon: товар едет обратно, надо принять и вернуть деньги (Django-команда sync_ozon_returns)',
        'script': '/app/manage.py',
        'args': ['sync_ozon_returns'],
    },
    {
        'id': 'horsebio_ozon_duplicates',
        'topic': 'Обновление данных',
        'name': 'Дубли заказов Ozon',
        'account': 'HorseBio',
        'schedule': 'Каждые 5 мин',
        'description': 'Переносит сведения об отправлении в заказ сайта и удаляет дубль, созданный синхронизацией МойСклад ↔ Ozon (Django-команда resolve_ozon_ms_duplicates)',
        'script': '/app/manage.py',
        'args': ['resolve_ozon_ms_duplicates', '--apply'],
    },
    {
        'id': 'horsebio_inventory_check',
        'topic': 'Обновление данных',
        'name': 'Инвентаризация',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:25',
        'description': 'Ежедневный пересчёт статуса инвентаризации позиций (Django-команда check_inventory)',
        'script': '/app/manage.py',
        'args': ['check_inventory', '--triggered-by', 'scheduler'],
    },
    {
        'id': 'horsebio_backup',
        'topic': 'Сохранность',
        'name': 'Бэкапы',
        'account': 'HorseBio',
        'schedule': 'Ежедн. в 09:50',
        'description': 'Идут ли бэкапы: свежесть последнего прогона, размер архивов, место на диске, давность проверки восстановлением',
        'script': '/app/moysklad/horsebio/02_checks/03_backup/scripts/01_check_backup.py',
        'args': [],
        'structured': True,
    },
]

SCRIPTS_BY_ID = {s['id']: s for s in SCRIPTS_CONFIG}


# Скрипт проверки здоровья — единственный со структурированными результатами
# и исключениями: перед запуском их выгружают из БД в data/*.json.
HEALTH_CHECK_SCRIPT_ID = 'horsebio_health_check'


def script_timeout(script_id):
    """Предельное время прогона в секундах."""
    return SCRIPTS_BY_ID.get(script_id, {}).get('timeout') or DEFAULT_TIMEOUT_SEC
