import PropTypes from 'prop-types';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell } from 'recharts';
import { formatNumber } from '../../utils/formatters';

const prepareChartData = (monthlyData) =>
    Object.entries(monthlyData).map(([month, quantity]) => ({ month, quantity: Number(quantity) }));

const prepareSeasonalData = (factors) => {
    const months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];
    return months.map((month, i) => ({ month, factor: factors[i + 1] }));
};

const tooltipStyle = { backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', padding: '10px 14px', fontFamily: 'var(--sans)', fontSize: 12 };

const CustomTooltip = ({ active, payload, label, valuePrefix = '', valueSuffix = '' }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={tooltipStyle}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
            {payload.map((e, i) => (
                <div key={i} style={{ color: e.color }}>{e.name}: {valuePrefix}{formatNumber(e.value)}{valueSuffix}</div>
            ))}
        </div>
    );
};

const sectionLabel = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '10px' };

export const SeasonalCharts = ({ data }) => {
    if (!data?.monthly_sales || !data?.seasonal_factors) return null;

    const salesData = prepareChartData(data.monthly_sales);
    const seasonalData = prepareSeasonalData(data.seasonal_factors);

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
            <div>
                <div style={sectionLabel}>Динамика продаж</div>
                <div style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={salesData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                            <XAxis dataKey="month" angle={-45} textAnchor="end" height={60} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <YAxis style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <Tooltip content={<CustomTooltip valueSuffix=" шт." />} />
                            <Legend wrapperStyle={{ fontFamily: 'var(--sans)', fontSize: 12 }} />
                            <Line type="monotone" dataKey="quantity" name="Продажи" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3 }} activeDot={{ r: 5 }} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div>
                <div style={sectionLabel}>Сезонные коэффициенты</div>
                <div style={{ height: 320 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={seasonalData} margin={{ top: 16, right: 16, left: 0, bottom: 0 }} barSize={36}>
                            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                            <XAxis dataKey="month" style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <YAxis domain={[0, Math.max(2, Math.ceil(Math.max(...seasonalData.map(d => d.factor))))]} ticks={[0, 0.5, 1, 1.5, 2]} style={{ fontFamily: 'var(--sans)', fontSize: 11 }} />
                            <Tooltip content={<CustomTooltip valuePrefix="×" valueSuffix=" от среднего" />} />
                            <Legend wrapperStyle={{ fontFamily: 'var(--sans)', fontSize: 12 }} />
                            <Bar dataKey="factor" name="Сезонный коэффициент" maxBarSize={50}>
                                {seasonalData.map((e, i) => (
                                    <Cell key={i} fill={e.factor >= 1.2 ? '#5cac6a' : e.factor <= 0.8 ? '#c64545' : '#5c8acc'} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', backgroundColor: 'var(--surface-soft)', padding: '12px 14px', borderRadius: '8px', lineHeight: 1.7 }}>
                <b style={{ color: 'var(--body)' }}>Как читать:</b> Коэффициент 1.0 = средний уровень · <span style={{ color: '#3a7c4a' }}>Зелёный ≥ 1.2</span> = пик · <span style={{ color: '#a03a3a' }}>Красный ≤ 0.8</span> = спад
            </div>
        </div>
    );
};

CustomTooltip.propTypes = { active: PropTypes.bool, payload: PropTypes.array, label: PropTypes.string, valuePrefix: PropTypes.string, valueSuffix: PropTypes.string };
SeasonalCharts.propTypes = { data: PropTypes.shape({ monthly_sales: PropTypes.object, seasonal_factors: PropTypes.object }) };

export default SeasonalCharts;
