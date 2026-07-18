import { useState, useEffect, useCallback } from 'react';
import { Download, X } from 'lucide-react';
import { ABCFilters } from './ABCFilters';
import { ABCStatistics } from './ABCStatistics';
import { ABCCharts } from './ABCCharts';
import { ABCTable } from './ABCTable';
import { FadeRise } from '../ui/motion';
import { Skeleton } from '../ui/Skeleton';
import { abcAnalysisApi } from '../../api/abcAnalysis';

const CATEGORIES = [
    { key: 'A', label: 'Категория A', desc: 'Ключевые продукты (80% выручки)', color: '#a0583e' },
    { key: 'B', label: 'Категория B', desc: 'Средние продукты (15% выручки)',  color: '#3a68a0' },
    { key: 'C', label: 'Категория C', desc: 'Редкие продукты (5% выручки)',    color: '#7a6010' },
];

const RECOMMENDATIONS = [
    { key: 'A', label: 'Категория A', color: '#a0583e', items: ['Постоянный контроль', 'Точный прогноз спроса', 'Частые поставки', 'Оптимальный запас'] },
    { key: 'B', label: 'Категория B', color: '#3a68a0', items: ['Периодический контроль', 'Средний запас', 'Регулярные поставки', 'Стандартный учёт'] },
    { key: 'C', label: 'Категория C', color: '#7a6010', items: ['Упрощённый контроль', 'Увеличенные партии', 'Редкие поставки', 'Минимальный запас'] },
];

const sectionCard    = { backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '10px', padding: '24px' };
const sectionHeading = { fontFamily: 'var(--serif)', fontSize: '22px', fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: '0 0 16px' };
const labelStyle     = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '12px' };

export const ABCAnalysis = () => {
    const [loading, setLoading] = useState(false);
    const [error, setError]     = useState(null);
    const [data, setData]       = useState(null);
    const [filters, setFilters] = useState({ periodMonths: 12, endDate: null });

    const fetchData = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await abcAnalysisApi.getAnalysis(filters);
            if (res.status === 'success') {
                const tableData = Object.entries(res.categories).flatMap(([category, cat]) =>
                    cat.products.map(p => ({
                        product: { id: p.id, name: p.name, article: p.article, group: p.group, subgroup: p.subgroup },
                        metrics: { category, ...p.metrics },
                    }))
                );
                setData({ ...res, tableData });
            } else {
                setError(res.message || 'Ошибка получения данных');
            }
        } catch (err) {
            setError(err.message || 'Ошибка получения данных');
        } finally {
            setLoading(false);
        }
    }, [filters]);

    useEffect(() => { fetchData(); }, [fetchData]);

    const handleExport = () => {
        const params = new URLSearchParams({
            period_months: filters.periodMonths,
            end_date: filters.endDate || '',
        });
        const link = document.createElement('a');
        link.href = `/api/analysis/abc/export/?${params}`;
        link.download = `abc_analysis_${new Date().toISOString().split('T')[0]}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', color: 'var(--ink)' }}>
            {/* Header */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
                <div>
                    <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: '0 0 4px' }}>
                        ABC-анализ продуктов
                    </h1>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                        Анализ продуктов по объёму продаж и выручке
                    </p>
                </div>
                <button
                    onClick={handleExport}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', height: '36px', padding: '0 16px', borderRadius: '8px', border: '1px solid var(--hairline)', backgroundColor: 'var(--canvas)', fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500, color: 'var(--ink)', cursor: 'pointer', transition: 'background-color 150ms', flexShrink: 0 }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-soft)'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'var(--canvas)'}
                >
                    <Download style={{ width: 14, height: 14 }} /> Экспорт
                </button>
            </div>

            {/* Category legend */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '12px' }}>
                {CATEGORIES.map(c => (
                    <div key={c.key} style={{ backgroundColor: 'var(--surface-soft)', borderRadius: '8px', padding: '14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: c.color }}>{c.label}</div>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.4 }}>{c.desc}</div>
                    </div>
                ))}
            </div>

            {/* Filters */}
            <FadeRise style={{ ...sectionCard, backgroundColor: 'var(--surface-soft)' }}>
                <div style={labelStyle}>Параметры анализа</div>
                <ABCFilters value={filters} onChange={setFilters} />
            </FadeRise>

            {/* Первая загрузка — скелетон страницы */}
            {loading && !data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }} aria-busy="true">
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                        <Skeleton height={380} style={{ borderRadius: 10 }} />
                        <Skeleton height={380} style={{ borderRadius: 10 }} />
                    </div>
                    <Skeleton height={280} style={{ borderRadius: 10 }} />
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

            {/* Content: при перезагрузке фильтров не размонтируем, а приглушаем */}
            {data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', opacity: loading ? 0.45 : 1, pointerEvents: loading ? 'none' : 'auto', transition: 'opacity 200ms ease' }}>
                    {/* Charts + Stats side by side */}
                    <FadeRise style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px' }}>
                        <div style={sectionCard}>
                            <h2 style={sectionHeading}>Распределение по категориям</h2>
                            <ABCCharts data={data} />
                        </div>
                        <div style={sectionCard}>
                            <h2 style={sectionHeading}>Статистика по категориям</h2>
                            <ABCStatistics data={data} />
                        </div>
                    </FadeRise>

                    {/* Table */}
                    <FadeRise inView style={sectionCard}>
                        <h2 style={sectionHeading}>Список продуктов</h2>
                        <ABCTable data={data.tableData} />
                    </FadeRise>

                    {/* Recommendations */}
                    <FadeRise inView style={{ ...sectionCard, backgroundColor: 'var(--surface-soft)' }}>
                        <div style={labelStyle}>Рекомендации по управлению</div>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
                            {RECOMMENDATIONS.map(r => (
                                <div key={r.key}>
                                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: r.color, marginBottom: '8px' }}>{r.label}</div>
                                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                        {r.items.map(item => (
                                            <li key={item} style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--body)', display: 'flex', gap: '5px' }}>
                                                <span style={{ color: 'var(--muted)', flexShrink: 0 }}>·</span> {item}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ))}
                        </div>
                    </FadeRise>
                </div>
            )}
        </div>
    );
};

export default ABCAnalysis;
