import {
    Home, Package, Users, Layers, Archive, Truck,
    BarChart2, TrendingUp, PackageCheck, PieChart, ShoppingCart, ShoppingBag,
    DollarSign, Factory, FileSpreadsheet, ClipboardList, Activity, Clock, ShieldCheck, Mail, KeyRound,
} from 'lucide-react';

// pageKey — ключ страницы из бэкенд-реестра (api/access.py). По нему фильтруется
// видимость пункта (постраничные права). Пункты без pageKey видны всегда.
const NAV_GROUPS = [
    {
        items: [
            { path: '/', label: 'Главная', icon: Home },
        ],
    },
    {
        label: 'Отгрузки',
        items: [
            { path: '/shipments/products',       label: 'Товары',       icon: Package, description: 'Анализ проданных товаров', pageKey: 'shipments-products' },
            { path: '/shipments/counterparties', label: 'Покупатели',   icon: Users, description: 'Клиенты и их покупки', pageKey: 'shipments-counterparties' },
            { path: '/shipments/materials',      label: 'Материалы',    icon: Layers, description: 'Расход материалов в продажах', pageKey: 'shipments-materials' },
            { path: '/deadlines',                label: 'Сроки оплаты', icon: Clock, description: 'Дебиторка с отсрочкой платежа', pageKey: 'deadlines' },
        ],
    },
    {
        label: 'Заказы сайта',
        items: [
            { path: '/site-orders', label: 'Заказы сайта', icon: Mail, description: 'Заказы с horse-bio.ru и их путь в МойСклад', pageKey: 'site-orders' },
        ],
    },
    {
        label: 'Приёмки',
        items: [
            { path: '/supplies/materials', label: 'Материалы',  icon: Archive, description: 'Поступления на склад', pageKey: 'supplies-materials' },
            { path: '/supplies/suppliers', label: 'Поставщики', icon: Truck, description: 'Контрагенты-поставщики', pageKey: 'supplies-suppliers' },
        ],
    },
    {
        label: 'Производство',
        items: [
            { path: '/production/calculator', label: 'Производство', icon: Factory, description: 'Расчёт сырья для производства', pageKey: 'production' },
        ],
    },
    {
        label: 'Инвентаризация',
        items: [
            { path: '/inventory', label: 'Мониторинг', icon: ClipboardList, description: 'Контроль позиций с 1-го числа месяца', pageKey: 'inventory' },
        ],
    },
    {
        label: 'Аналитика',
        items: [
            { path: '/analysis/abc',                 label: 'ABC Анализ',       icon: BarChart2, description: 'Категоризация по продажам', pageKey: 'abc' },
            { path: '/analysis/seasonal',            label: 'Сезонность',       icon: TrendingUp, description: 'Паттерны продаж по времени', pageKey: 'seasonal' },
            { path: '/analysis/fbo',                 label: 'FBO Заказы',       icon: PackageCheck, description: 'Планирование FBO заказов', pageKey: 'fbo' },
            { path: '/analysis/counterparty-groups', label: 'Группы клиентов',  icon: PieChart, description: 'Сегментация клиентов', pageKey: 'counterparty-groups' },
            { path: '/purchases/analysis',           label: 'Помощник закупок', icon: ShoppingCart, description: 'Рекомендации по закупкам', pageKey: 'purchases' },
            { path: '/ozon/fbo-converter',           label: 'FBO Конвертер',    icon: FileSpreadsheet, description: 'Конвертация прогноза в шаблон Ozon', pageKey: 'ozon-fbo-converter' },
            { path: '/analysis/ozon',                label: 'Ozon',             icon: ShoppingBag, description: 'Отчёты по рекламе и продажам', pageKey: 'ozon' },
            { path: '/analysis/cash-flow',           label: 'ДДС',              icon: DollarSign, description: 'Мониторинг денежных потоков', pageKey: 'cash-flow' },
            { path: '/analysis/cash-flow-v2',        label: 'ДДС · новая',      icon: DollarSign, description: 'ДДС с разбивкой по группам контрагента (тест)', pageKey: 'cash-flow-v2' },
        ],
    },
    {
        label: 'Администрирование',
        superuserOnly: true,
        items: [
            { path: '/admin/access',     label: 'Доступы',           icon: KeyRound, description: 'Кто какие страницы видит', superuserOnly: true },
            { path: '/checks',           label: 'Проверки',          icon: ShieldCheck, description: 'Автоматические проверки МойСклад', superuserOnly: true },
            { path: '/system/analytics', label: 'Аналитика системы', icon: Activity, description: 'Использование системы и сессии', superuserOnly: true },
        ],
    },
];

export default NAV_GROUPS;
