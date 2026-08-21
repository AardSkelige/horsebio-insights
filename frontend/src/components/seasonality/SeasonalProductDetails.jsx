import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Loader2, Activity, TrendingUp, Box, Calendar, AlertTriangle } from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { StatCard, StatGrid } from '../ui';
import { formatNumber } from '../../utils/formatters';
import { CHART_ANIMATION } from '../../utils/chartAnimation';

const MonthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const SEASONALITY_INFO = {
    STABLE:     { title: 'Стабильные продажи',    color: 'var(--info-ink)', bg: 'var(--info-bg)',  border: 'var(--info-border)' },
    SUMMER:     { title: 'Летний сезон',           color: 'var(--cat-orange-ink)', bg: 'var(--cat-orange-bg)',  border: 'var(--cat-orange-border)' },
    WINTER:     { title: 'Зимний сезон',           color: 'var(--cat-teal-ink)', bg: 'var(--cat-teal-bg)',  border: 'var(--cat-teal-border)' },
    MULTI_PEAK: { title: 'Несколько пиков',        color: 'var(--cat-violet-ink)', bg: 'var(--cat-violet-bg)',  border: 'var(--cat-violet-border)' },
    UNCERTAIN:  { title: 'Неопределённая сез-ть', color: 'var(--muted)', bg: 'var(--surface-card)', border: 'var(--hairline)' },
};

const RECOMMENDATIONS = {
    STABLE:     ['Поддерживайте постоянный уровень запасов', 'Используйте равномерные интервалы поставок', 'Страховой запас: 20–30% от среднемесячных продаж'],
    SUMMER:     ['Увеличьте запасы перед летним сезоном', 'Начните накопление за 2–3 месяца до пика', 'Страховой запас летом: 40–50% от среднемесячных продаж'],
    WINTER:     ['Увеличьте запасы перед зимним сезоном', 'Начните накопление за 2–3 месяца до пика', 'Страховой запас зимой: 40–50% от среднемесячных продаж'],
    MULTI_PEAK: ['Следите за календарём пиков продаж', 'Корректируйте запасы за 1–2 месяца до каждого пика', 'Используйте динамический страховой запас'],
    UNCERTAIN:  ['Держите повышенный страховой запас', 'Чаще проводите мониторинг продаж', 'Используйте короткие интервалы поставок'],
};


const tooltipStyle = { backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', padding: '10px 14px', fontFamily: 'var(--sans)', fontSize: 12 };

const chartLabel = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '10px' };

const DotComponent = ({ payload, cx, cy }) => {
    if (!payload || !cx || !cy) return null;
    return <circle cx={cx} cy={cy} r={payload.isSignificant ? 5 : 3} fill="var(--chart-2)" />;
};

const SeasonalProductDetails = ({ data, loading, error }) => {
    const [salesData, setSalesData] = useState([]);
    const [factorsData, setFactorsData] = useState([]);

    useEffect(() => {
        if (data?.monthly_sales) {
            setSalesData(Object.entries(data.monthly_sales).map(([date, quantity]) => ({ date, quantity })));
        }
        if (data?.seasonal_factors) {
            setFactorsData(Object.entries(data.seasonal_factors).map(([month, factor]) => ({
                month: MonthNames[parseInt(month) - 1],
                factor,
                isSignificant: factor < 0.8 || factor > 1.2,
            })));
        }
    }, [data]);

    if (loading) return (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '160px', gap: '10px' }}>
            <Loader2 style={{ width: 20, height: 20, color: 'var(--primary)' }} className="animate-spin" />
            <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--muted)' }}>Загрузка...</span>
        </div>
    );

    if (error) return (
        <div style={{ padding: '12px 16px', backgroundColor: 'var(--error-bg)', border: '1px solid var(--error-border)', borderRadius: '8px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--error)' }}>
            {error}
        </div>
    );

    if (!data) return null;

    const info = data.seasonality_type ? SEASONALITY_INFO[data.seasonality_type] : null;
    const recs = data.seasonality_type ? RECOMMENDATIONS[data.seasonality_type] : [];

    const fmtDate = (v) => {
        const d = new Date(v);
        return `${MonthNames[d.getMonth()].slice(0, 3)} ${d.getFullYear()}`;
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div>
                    <div style={{ fontFamily: 'var(--serif)', fontSize: '20px', fontWeight: 400, color: 'var(--ink)' }}>{data.name || 'Загрузка...'}</div>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', marginTop: 2 }}>Артикул: {data.article || '—'}</div>
                </div>
                {info && (
                    <span style={{ display: 'inline-block', padding: '4px 12px', borderRadius: '20px', fontSize: '12px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: info.bg, color: info.color, border: `1px solid ${info.border}` }}>
                        {info.title}
                    </span>
                )}
            </div>

            {/* Stats */}
            <StatGrid>
                <StatCard tone="dark" icon={Activity}   value={formatNumber(data.sales_stats?.total_quantity || 0)}      title="Общий объём продаж" />
                <StatCard tone="dark" icon={TrendingUp} value={formatNumber(data.sales_stats?.avg_monthly_quantity || 0)} title="Среднемесячные продажи" />
                <StatCard tone="dark" icon={Box}        value={formatNumber(data.sales_stats?.orders_count || 0)}         title="Количество заказов" />
                <StatCard tone="dark" icon={Calendar}   value={(data.stability_metrics?.coefficient_std || 0).toFixed(2)} title="Коэф. стабильности" />
            </StatGrid>

            {/* Charts */}
            {salesData.length > 0 && (
                <div>
                    <div style={chartLabel}>Динамика продаж</div>
                    <div style={{ height: 300 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={salesData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                <XAxis dataKey="date" tickFormatter={fmtDate} angle={-45} textAnchor="end" height={70} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                <YAxis style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                <Tooltip contentStyle={tooltipStyle} formatter={v => [formatNumber(v), 'Количество']} labelFormatter={fmtDate} />
                                <Line {...CHART_ANIMATION} type="monotone" dataKey="quantity" name="Количество" stroke="var(--primary)" strokeWidth={2} dot={<DotComponent />} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {factorsData.length > 0 && (
                <div>
                    <div style={chartLabel}>Сезонные коэффициенты</div>
                    <div style={{ height: 280 }}>
                        <ResponsiveContainer width="100%" height="100%">
                            <LineChart data={factorsData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                <XAxis dataKey="month" style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                <YAxis domain={[0.5, 1.5]} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                                <Tooltip contentStyle={tooltipStyle} formatter={v => [`×${v.toFixed(3)}`, 'Коэффициент']} />
                                <Line {...CHART_ANIMATION} type="monotone" dataKey="factor" name="Коэффициент" stroke="var(--chart-2)" strokeWidth={2} dot={<DotComponent />} />
                            </LineChart>
                        </ResponsiveContainer>
                    </div>
                </div>
            )}

            {/* Seasonality analysis */}
            {info && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', backgroundColor: 'var(--surface-soft)', borderRadius: '10px', padding: '18px' }}>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)' }}>Анализ сезонности</div>
                    <div>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>Тип: </span>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: info.color }}>{info.title}</span>
                    </div>
                    {data.peaks?.length > 0 && (
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>Пики продаж</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {data.peaks.map((p, i) => (
                                    <span key={i} title={`+${p.deviation_percent.toFixed(1)}%`} style={{ padding: '3px 9px', borderRadius: '20px', fontSize: '12px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: 'var(--success-bg)', color: 'var(--success-ink)', border: '1px solid var(--success-border)' }}>
                                        {MonthNames[(p.month || 0) - 1]}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                    {data.troughs?.length > 0 && (
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', marginBottom: '6px' }}>Спады продаж</div>
                            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {data.troughs.map((t, i) => (
                                    <span key={i} title={`${t.deviation_percent.toFixed(1)}%`} style={{ padding: '3px 9px', borderRadius: '20px', fontSize: '12px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: 'var(--error-bg)', color: 'var(--error-ink)', border: '1px solid var(--error-border)' }}>
                                        {MonthNames[(t.month || 0) - 1]}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Recommendations */}
            {recs.length > 0 && (
                <div style={{ backgroundColor: 'var(--accent-wash)', border: '1px solid var(--accent-border)', borderRadius: '10px', padding: '18px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '7px', fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 600, color: 'var(--primary)', marginBottom: '10px' }}>
                        <AlertTriangle style={{ width: 14, height: 14 }} /> Рекомендации по управлению запасами
                    </div>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '5px' }}>
                        {recs.map((r, i) => (
                            <li key={i} style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)', display: 'flex', gap: '6px' }}>
                                <span style={{ color: 'var(--primary)', flexShrink: 0 }}>·</span> {r}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
};

DotComponent.propTypes = { payload: PropTypes.shape({ isSignificant: PropTypes.bool }), cx: PropTypes.number, cy: PropTypes.number };
StatCard.propTypes = { Icon: PropTypes.elementType, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]), label: PropTypes.string };
SeasonalProductDetails.propTypes = { data: PropTypes.object, loading: PropTypes.bool.isRequired, error: PropTypes.string };

export default SeasonalProductDetails;
