import { useState, useEffect, useRef } from 'react';
import {
    PackageIcon, BuildingIcon, BoxIcon, UsersIcon,
    ChartPieIcon, TrendingUp, ShoppingCart, ShoppingBagIcon,
    DollarSign, Factory, ShieldCheck, FileSpreadsheet, ClipboardList,
    BarChart2, PackageCheck, Clock,
} from 'lucide-react';
import FeatureCard from './components/FeatureCard';
import StatisticsCards from './components/StatisticsCards';
import { statsApi } from '../../api/statsApi';
import { authApi } from '../../api/authApi';
import { useLoading } from '../../contexts/LoadingContext';

const BASE_SECTIONS = [
    {
        title: 'Отгрузки',
        items: [
            { icon: BoxIcon,     title: 'Товары',        description: 'Анализ проданных товаров',            link: '/shipments/products' },
            { icon: UsersIcon,   title: 'Покупатели',    description: 'Клиенты и их покупки',                link: '/shipments/counterparties' },
            { icon: PackageIcon, title: 'Материалы',     description: 'Расход материалов в продажах',        link: '/shipments/materials' },
            { icon: Clock,       title: 'Сроки оплаты',  description: 'Дебиторка с отсрочкой платежа',       link: '/deadlines' },
        ],
    },
    {
        title: 'Приёмки',
        items: [
            { icon: PackageIcon,  title: 'Материалы',  description: 'Поступления на склад',      link: '/supplies/materials' },
            { icon: BuildingIcon, title: 'Поставщики', description: 'Контрагенты-поставщики',    link: '/supplies/suppliers' },
        ],
    },
    {
        title: 'Производство',
        items: [
            { icon: Factory, title: 'Производство', description: 'Расчёт сырья для производства', link: '/production/calculator' },
        ],
    },
    {
        title: 'Инвентаризация',
        items: [
            { icon: ClipboardList, title: 'Мониторинг', description: 'Контроль позиций с 1-го числа месяца', link: '/inventory' },
        ],
    },
    {
        title: 'Аналитика',
        items: [
            { icon: BarChart2,       title: 'ABC-анализ',          description: 'Категоризация по продажам',          link: '/analysis/abc' },
            { icon: TrendingUp,      title: 'Сезонный анализ',     description: 'Паттерны продаж по времени',        link: '/analysis/seasonal' },
            { icon: PackageCheck,    title: 'FBO Заказы',          description: 'Планирование FBO заказов',          link: '/analysis/fbo' },
            { icon: ChartPieIcon,    title: 'Группы контрагентов', description: 'Сегментация клиентов',              link: '/analysis/counterparty-groups' },
            { icon: ShoppingCart,    title: 'Помощник закупок',    description: 'Рекомендации по закупкам',          link: '/purchases/analysis' },
            { icon: FileSpreadsheet, title: 'FBO Конвертер',       description: 'Конвертация прогноза в шаблон Ozon', link: '/ozon/fbo-converter' },
            { icon: ShoppingBagIcon, title: 'Аналитика OZON',      description: 'Отчёты по рекламе и продажам',     link: '/analysis/ozon' },
            { icon: DollarSign,      title: 'Движение ДС',         description: 'Мониторинг денежных потоков',      link: '/analysis/cash-flow' },
        ],
    },
];

const HomePage = () => {
    const [stats, setStats] = useState(null);
    const [isSuperuser, setIsSuperuser] = useState(false);
    const abortRef = useRef(null);
    const { syncVersion } = useLoading();

    useEffect(() => {
        abortRef.current = new AbortController();
        const { signal } = abortRef.current;

        statsApi.get(signal)
            .then(data => { if (data.status === 'success') setStats(data.stats); })
            .catch(() => {});

        return () => abortRef.current?.abort();
    }, [syncVersion]);

    useEffect(() => {
        abortRef.current = new AbortController();
        const { signal } = abortRef.current;

        authApi.check(signal)
            .then(d => setIsSuperuser(!!d.isSuperuser))
            .catch(() => {});

        return () => abortRef.current?.abort();
    }, []);

    const moyskladItems = isSuperuser ? [
        { icon: ShieldCheck, title: 'Проверки', description: 'Автоматические проверки МойСклад', link: '/checks' },
    ] : [];

    const sections = [
        ...BASE_SECTIONS,
        ...(moyskladItems.length ? [{ title: 'МойСклад', items: moyskladItems }] : []),
    ];

    return (
        <div style={{ color: 'var(--ink)' }} className="space-y-10">

            {stats && (
                <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
                        <span style={{ fontSize: '11px', fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                            Статистика
                        </span>
                        <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--hairline)' }} />
                    </div>
                    <StatisticsCards stats={stats} />
                </div>
            )}

            <div className="space-y-8">
                {sections.map((section) => (
                    <div key={section.title}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '14px' }}>
                            <span style={{ fontSize: '11px', fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                                {section.title}
                            </span>
                            <div style={{ flex: 1, height: '1px', backgroundColor: 'var(--hairline)' }} />
                        </div>
                        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                            {section.items.map((item) => (
                                <FeatureCard key={item.link} {...item} />
                            ))}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
};

export default HomePage;
