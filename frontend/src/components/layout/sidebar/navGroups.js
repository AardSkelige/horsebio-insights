import {
    Home, Package, Users, Layers, Archive, Truck,
    BarChart2, TrendingUp, PackageCheck, PieChart, ShoppingCart, ShoppingBag,
    DollarSign, Factory, FileSpreadsheet, ClipboardList, Activity, Clock, ShieldCheck,
} from 'lucide-react';

const NAV_GROUPS = [
    {
        items: [
            { path: '/', label: 'Главная', icon: Home },
        ],
    },
    {
        label: 'Отгрузки',
        items: [
            { path: '/shipments/products',       label: 'Товары',       icon: Package, description: 'Анализ проданных товаров' },
            { path: '/shipments/counterparties', label: 'Покупатели',   icon: Users, description: 'Клиенты и их покупки' },
            { path: '/shipments/materials',      label: 'Материалы',    icon: Layers, description: 'Расход материалов в продажах' },
            { path: '/deadlines',                label: 'Сроки оплаты', icon: Clock, description: 'Дебиторка с отсрочкой платежа' },
        ],
    },
    {
        label: 'Приёмки',
        items: [
            { path: '/supplies/materials', label: 'Материалы',  icon: Archive, description: 'Поступления на склад' },
            { path: '/supplies/suppliers', label: 'Поставщики', icon: Truck, description: 'Контрагенты-поставщики' },
        ],
    },
    {
        label: 'Производство',
        items: [
            { path: '/production/calculator', label: 'Производство', icon: Factory, description: 'Расчёт сырья для производства' },
        ],
    },
    {
        label: 'Инвентаризация',
        items: [
            { path: '/inventory', label: 'Мониторинг', icon: ClipboardList, description: 'Контроль позиций с 1-го числа месяца' },
        ],
    },
    {
        label: 'Аналитика',
        items: [
            { path: '/analysis/abc',                 label: 'ABC Анализ',       icon: BarChart2, description: 'Категоризация по продажам' },
            { path: '/analysis/seasonal',            label: 'Сезонность',       icon: TrendingUp, description: 'Паттерны продаж по времени' },
            { path: '/analysis/fbo',                 label: 'FBO Заказы',       icon: PackageCheck, description: 'Планирование FBO заказов' },
            { path: '/analysis/counterparty-groups', label: 'Группы клиентов',  icon: PieChart, description: 'Сегментация клиентов' },
            { path: '/purchases/analysis',           label: 'Помощник закупок', icon: ShoppingCart, description: 'Рекомендации по закупкам' },
            { path: '/ozon/fbo-converter',           label: 'FBO Конвертер',    icon: FileSpreadsheet, description: 'Конвертация прогноза в шаблон Ozon' },
            { path: '/analysis/ozon',                label: 'Ozon',             icon: ShoppingBag, description: 'Отчёты по рекламе и продажам' },
            { path: '/analysis/cash-flow',           label: 'ДДС',              icon: DollarSign, description: 'Мониторинг денежных потоков' },
        ],
    },
    {
        label: 'МойСклад',
        items: [
            { path: '/checks', label: 'Проверки', icon: ShieldCheck, description: 'Автоматические проверки МойСклад', superuserOnly: true },
        ],
    },
    {
        label: 'Система',
        superuserOnly: true,
        items: [
            { path: '/system/analytics', label: 'Аналитика системы', icon: Activity, description: 'Использование системы и сессии', superuserOnly: true },
        ],
    },
];

export default NAV_GROUPS;
