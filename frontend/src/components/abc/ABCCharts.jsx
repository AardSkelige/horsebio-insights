import PropTypes from 'prop-types';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts';
import { CHART_ANIMATION } from '../../utils/chartAnimation';

const COLORS = { A: '#cc785c', B: '#5c8acc', C: '#cc9c3a' };

const fmtCurrency = (v) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v);

const CustomTooltip = ({ active, payload }) => {
    if (!(active && payload?.length)) return null;
    const d = payload[0].payload;
    return (
        <div style={{ backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', padding: '12px 14px', fontFamily: 'var(--sans)', fontSize: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.08)' }}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{d.name}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, color: 'var(--body)' }}>
                <span>Выручка: <b>{fmtCurrency(d.value)}</b></span>
                <span>Доля: <b>{d.percent.toFixed(1)}%</b></span>
                <span>Продуктов: <b>{d.products}</b></span>
            </div>
        </div>
    );
};

export const ABCCharts = ({ data }) => {
    if (!data?.categories) return null;

    const pieData = Object.entries(data.categories).map(([category, cat]) => ({
        name: `Категория ${category}`,
        value: cat.metrics.revenue,
        percent: cat.metrics.revenue_share * 100,
        products: cat.metrics.product_count,
        category,
    }));

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ height: 320 }}>
                <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                        <Pie {...CHART_ANIMATION} data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={110} dataKey="value" labelLine={false}>
                            {pieData.map(e => <Cell key={e.category} fill={COLORS[e.category]} />)}
                        </Pie>
                        <Legend
                            layout="horizontal" align="center" verticalAlign="bottom"
                            formatter={(v, e) => `${v} (${e.payload.percent.toFixed(1)}%)`}
                            wrapperStyle={{ fontFamily: 'var(--sans)', fontSize: 12, paddingTop: 8 }}
                        />
                        <Tooltip content={<CustomTooltip />} />
                    </PieChart>
                </ResponsiveContainer>
            </div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>
                Диаграмма показывает распределение выручки между категориями. Наведите на сегменты для подробной информации.
            </div>
        </div>
    );
};

CustomTooltip.propTypes = { active: PropTypes.bool, payload: PropTypes.array };
ABCCharts.propTypes = { data: PropTypes.shape({ categories: PropTypes.object.isRequired }) };

export default ABCCharts;
