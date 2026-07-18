import PropTypes from 'prop-types';
import {
    PieChart, Pie, Cell, ResponsiveContainer,
    Tooltip as RechartsTooltip, Legend,
    BarChart, Bar, XAxis, YAxis, CartesianGrid
} from 'recharts';
import { formatCurrency } from '../../utils/formatters';
import { CHART_ANIMATION } from '../../utils/chartAnimation';

const COLORS = {
    large:      '#cc785c',
    medium:     '#5c8acc',
    small:      '#5cac6a',
    rare_large: '#8c8a84',
};

const CATEGORY_NAMES = {
    large:      'Крупные (регулярные)',
    medium:     'Средние (регулярные)',
    small:      'Мелкие (нерегулярные)',
    rare_large: 'Крупные (редкие)',
};

const CATEGORY_DESCRIPTIONS = {
    large:      'Основные клиенты с высоким объемом регулярных закупок',
    medium:     'Стабильные клиенты со средним объемом закупок',
    small:      'Клиенты с небольшим объемом нерегулярных закупок',
    rare_large: 'Клиенты с большими, но редкими закупками',
};

const tooltipStyle = {
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '8px', padding: '12px 14px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
};

const ChartTooltip = ({ active, payload }) => {
    if (!(active && payload?.length)) return null;
    const d = payload[0].payload;
    return (
        <div style={tooltipStyle}>
            <div style={{ fontWeight: 600, marginBottom: 6 }}>{d.name}</div>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginBottom: 8 }}>{CATEGORY_DESCRIPTIONS[d.category]}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 12 }}>
                <span>Объём: <b>{formatCurrency(d.total_monthly_volume)}</b></span>
                <span>Доля: <b>{(d.volume_share * 100).toFixed(1)}%</b></span>
                <span>Контрагентов: <b>{d.counterparties_count}</b></span>
                <span>Активность: <b>{(d.avg_frequency * 100).toFixed(1)}%</b></span>
            </div>
        </div>
    );
};

const sectionLabel = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '12px' };

export const CounterpartyGroupsCharts = ({ data }) => {
    if (!data?.categories) return null;

    const totalVolume = Object.values(data.categories).reduce((s, c) => s + c.total_monthly_volume, 0);
    const chartData = Object.entries(data.categories).map(([category, cat]) => ({
        category,
        name: CATEGORY_NAMES[category],
        total_monthly_volume: cat.total_monthly_volume,
        volume_share: totalVolume ? cat.total_monthly_volume / totalVolume : 0,
        counterparties_count: cat.counterparties_count,
        avg_frequency: cat.avg_frequency,
    }));

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <div>
                <div style={sectionLabel}>Распределение объёма продаж</div>
                <div style={{ height: 280 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                            <Pie {...CHART_ANIMATION} data={chartData} cx="50%" cy="50%" innerRadius={60} outerRadius={100} dataKey="total_monthly_volume" labelLine={false}>
                                {chartData.map(e => <Cell key={e.category} fill={COLORS[e.category]} />)}
                            </Pie>
                            <RechartsTooltip content={<ChartTooltip />} />
                            <Legend
                                formatter={(value, entry) => `${value} (${(entry.payload.volume_share * 100).toFixed(1)}%)`}
                                wrapperStyle={{ fontFamily: 'var(--sans)', fontSize: 12 }}
                            />
                        </PieChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div>
                <div style={sectionLabel}>Активность по группам</div>
                <div style={{ height: 280 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} margin={{ top: 20, right: 16, left: 0, bottom: 60 }} barSize={36}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                            <XAxis dataKey="name" angle={-30} textAnchor="end" interval={0} height={60} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <YAxis tickFormatter={v => `${(v * 100).toFixed(0)}%`} domain={[0, 1]} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <RechartsTooltip
                                formatter={v => [`${(v * 100).toFixed(1)}%`, 'Активность']}
                                labelFormatter={l => `Группа: ${l}`}
                                contentStyle={{ fontFamily: 'var(--sans)', fontSize: 12, borderRadius: 8, border: '1px solid var(--hairline)' }}
                            />
                            <Bar {...CHART_ANIMATION} dataKey="avg_frequency" name="Активность">
                                {chartData.map(e => <Cell key={e.category} fill={COLORS[e.category]} />)}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </div>
    );
};

ChartTooltip.propTypes = {
    active: PropTypes.bool,
    payload: PropTypes.array,
};

CounterpartyGroupsCharts.propTypes = {
    data: PropTypes.shape({
        categories: PropTypes.objectOf(PropTypes.shape({
            total_monthly_volume: PropTypes.number.isRequired,
            counterparties_count: PropTypes.number.isRequired,
            avg_frequency: PropTypes.number.isRequired,
        })).isRequired,
    }).isRequired,
};

export default CounterpartyGroupsCharts;
