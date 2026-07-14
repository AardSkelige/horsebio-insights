import { useState, useEffect, useCallback } from 'react';
import { Loader2, X } from 'lucide-react';
import { CounterpartyGroupsFilters } from './CounterpartyGroupsFilters';
import { CounterpartyGroupsStats } from './CounterpartyGroupsStats';
import { CounterpartyGroupsCharts } from './CounterpartyGroupsCharts';
import { CounterpartyGroupsTable } from './CounterpartyGroupsTable';
import { counterpartiesApi } from '../../api/counterpartiesApi';

const GROUPS = [
    { key: 'large',      label: 'Крупные (регулярные)',    desc: 'Основные клиенты с высоким объёмом регулярных закупок' },
    { key: 'medium',     label: 'Средние (регулярные)',    desc: 'Стабильные клиенты со средним объёмом закупок' },
    { key: 'small',      label: 'Мелкие (нерегулярные)',   desc: 'Клиенты с небольшим объёмом нерегулярных закупок' },
    { key: 'rare_large', label: 'Крупные (редкие)',        desc: 'Клиенты с большими, но редкими закупками' },
];

const GROUP_COLORS = {
    large: 'var(--primary)', medium: '#5c8acc', small: '#5cac6a', rare_large: 'var(--muted)',
};

const RECOMMENDATIONS = [
    { key: 'large',      label: 'Крупные (регулярные)',  items: ['Индивидуальный подход', 'Особые условия работы', 'Приоритетное обслуживание', 'Регулярный контакт'] },
    { key: 'medium',     label: 'Средние (регулярные)',  items: ['Стандартные условия', 'Периодический контакт', 'Программы лояльности', 'Потенциал роста'] },
    { key: 'small',      label: 'Мелкие (нерегулярные)', items: ['Автоматизация работы', 'Типовые предложения', 'Онлайн поддержка', 'Акции и спецпредложения'] },
    { key: 'rare_large', label: 'Крупные (редкие)',      items: ['Анализ потребностей', 'Специальные условия', 'Планирование закупок', 'Работа над частотой'] },
];

const sectionCard = { backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px', padding: '24px' };
const sectionHeading = { fontFamily: 'var(--serif)', fontSize: '22px', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: '0 0 16px' };
const labelStyle = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '12px' };

export const CounterpartyGroupsAnalysis = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [data, setData] = useState(null);
    const [filters, setFilters] = useState({ periodMonths: 12, endDate: null });

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams({ period_months: filters.periodMonths, end_date: filters.endDate || '' });
            const result = await counterpartiesApi.getGroups(params);
            if (result.status === 'success') setData(result.data);
            else setError(result.message || 'Ошибка получения данных');
        } catch (err) {
            setError(err.message || 'Ошибка получения данных');
        } finally {
            setLoading(false);
        }
    }, [filters]);

    useEffect(() => { fetchData(); }, [fetchData]);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', color: 'var(--ink)' }}>
            {/* Header */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px' }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: '0 0 4px' }}>
                    Группы контрагентов
                </h1>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                    Анализ клиентской базы по объёму закупок и частоте заказов
                </p>
            </div>

            {/* Group legend */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '12px' }}>
                {GROUPS.map(g => (
                    <div key={g.key} style={{ backgroundColor: 'var(--surface-soft)', borderRadius: '8px', padding: '14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: GROUP_COLORS[g.key] }}>{g.label}</div>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.4 }}>{g.desc}</div>
                    </div>
                ))}
            </div>

            {/* Filters */}
            <div style={{ ...sectionCard, backgroundColor: 'var(--surface-soft)' }}>
                <div style={labelStyle}>Параметры анализа</div>
                <CounterpartyGroupsFilters value={filters} onChange={setFilters} />
            </div>

            {/* Loading */}
            {loading && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '48px 0', gap: '10px' }}>
                    <Loader2 style={{ width: 20, height: 20, color: 'var(--primary)' }} className="animate-spin" />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--muted)' }}>Загрузка данных...</span>
                </div>
            )}

            {/* Error */}
            {error && !loading && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '12px 16px', backgroundColor: 'rgba(198,69,69,0.08)', border: '1px solid rgba(198,69,69,0.3)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: '#c64545' }}>
                    <span style={{ flex: 1 }}><b>Ошибка загрузки данных:</b> {error}</span>
                    <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#c64545', padding: 0, flexShrink: 0 }}>
                        <X style={{ width: 14, height: 14 }} />
                    </button>
                </div>
            )}

            {/* Content */}
            {!loading && data && (
                <>
                    {/* Charts */}
                    <div style={sectionCard}>
                        <h2 style={sectionHeading}>Распределение по группам</h2>
                        <CounterpartyGroupsCharts data={data} />
                    </div>

                    {/* Stats */}
                    <div style={sectionCard}>
                        <h2 style={sectionHeading}>Статистика по группам</h2>
                        <CounterpartyGroupsStats data={data} />
                    </div>

                    {/* Table */}
                    <div style={sectionCard}>
                        <h2 style={sectionHeading}>Список контрагентов</h2>
                        <CounterpartyGroupsTable data={data} />
                    </div>

                    {/* Recommendations */}
                    <div style={{ ...sectionCard, backgroundColor: 'var(--surface-soft)' }}>
                        <div style={labelStyle}>Рекомендации по работе с группами</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
                            {RECOMMENDATIONS.map(r => (
                                <div key={r.key}>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: GROUP_COLORS[r.key], marginBottom: '8px' }}>{r.label}</div>
                                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                        {r.items.map(item => (
                                            <li key={item} style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--body)', display: 'flex', alignItems: 'flex-start', gap: '5px' }}>
                                                <span style={{ color: 'var(--muted)', flexShrink: 0 }}>·</span> {item}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </div>
                </>
            )}
        </div>
    );
};

export default CounterpartyGroupsAnalysis;
