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
            { path: '/shipments/products',       label: 'Товары',       icon: Package },
            { path: '/shipments/counterparties', label: 'Покупатели',   icon: Users },
            { path: '/shipments/materials',      label: 'Материалы',    icon: Layers },
            { path: '/deadlines',                label: 'Сроки оплаты', icon: Clock },
        ],
    },
    {
        label: 'Приёмки',
        items: [
            { path: '/supplies/materials', label: 'Материалы',  icon: Archive },
            { path: '/supplies/suppliers', label: 'Поставщики', icon: Truck },
        ],
    },
    {
        label: 'Производство',
        items: [
            { path: '/production/calculator', label: 'Производство', icon: Factory },
        ],
    },
    {
        label: 'Инвентаризация',
        items: [
            { path: '/inventory', label: 'Мониторинг', icon: ClipboardList },
        ],
    },
    {
        label: 'Аналитика',
        items: [
            { path: '/analysis/abc',                 label: 'ABC Анализ',        icon: BarChart2 },
            { path: '/analysis/seasonal',            label: 'Сезонность',        icon: TrendingUp },
            { path: '/analysis/fbo',                 label: 'FBO Заказы',        icon: PackageCheck },
            { path: '/analysis/counterparty-groups', label: 'Группы клиентов',   icon: PieChart },
            { path: '/purchases/analysis',           label: 'Помощник закупок',  icon: ShoppingCart },
            { path: '/ozon/fbo-converter',           label: 'FBO Конвертер',     icon: FileSpreadsheet },
            { path: '/analysis/ozon',                label: 'Ozon',              icon: ShoppingBag },
            { path: '/analysis/cash-flow',           label: 'ДДС',               icon: DollarSign },
        ],
    },
    {
        label: 'МойСклад',
        items: [
            { path: '/checks', label: 'Проверки', icon: ShieldCheck, superuserOnly: true },
        ],
    },
    {
        label: 'Система',
        superuserOnly: true,
        items: [
            { path: '/system/analytics', label: 'Аналитика системы', icon: Activity, superuserOnly: true },
        ],
    },
];

export default NAV_GROUPS;
