import PropTypes from 'prop-types';
import { Activity, TrendingUp, TrendingDown, Clock } from 'lucide-react';
import { formatNumber, formatCurrency } from '../../utils/formatters';

const StatCard = ({ label, value, suffix, Icon }) => (
    <div style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '10px', padding: '18px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--on-dark-soft)' }}>
            {Icon && <Icon style={{ width: 12, height: 12 }} />}{label}
        </div>
        <div style={{ fontFamily: 'var(--serif)', fontSize: '22px', fontWeight: 400, color: 'var(--on-dark)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1', lineHeight: 1 }}>
            {value}{suffix && <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', marginLeft: '5px', color: 'var(--on-dark-soft)' }}>{suffix}</span>}
        </div>
    </div>
);

const PeakTag = ({ label, deviation, isHigh }) => (
    <span title={`Отклонение: ${isHigh ? '+' : ''}${deviation.toFixed(1)}%`} style={{ display: 'inline-block', padding: '3px 9px', borderRadius: '20px', fontSize: '12px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: isHigh ? 'rgba(92,172,106,0.12)' : 'rgba(198,69,69,0.1)', color: isHigh ? '#3a7c4a' : '#a03a3a', border: `1px solid ${isHigh ? 'rgba(92,172,106,0.3)' : 'rgba(198,69,69,0.3)'}` }}>
        {label}
    </span>
);

const labelStyle = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '5px' };

export const SeasonalStatistics = ({ data }) => {
    if (!data) {
        return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 0', gap: '8px' }}>
                <Activity style={{ width: 40, height: 40, color: 'var(--hairline)' }} />
                <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: 'var(--muted)' }}>Выберите продукт для просмотра статистики</span>
            </div>
        );
    }

    if (!data.name || !data.peaks || !data.troughs || !data.stability_metrics) {
        return (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 0', gap: '8px' }}>
                <Activity style={{ width: 40, height: 40, color: 'var(--hairline)' }} />
                <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', color: '#c64545' }}>Ошибка загрузки данных продукта</span>
            </div>
        );
    }

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div>
                <div style={{ fontFamily: 'var(--serif)', fontSize: '20px', fontWeight: 400, color: 'var(--ink)', margin: '0 0 2px' }}>{data.name}</div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>Артикул: {data.article}</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '12px' }}>
                <StatCard label="Среднемесячные продажи" value={formatNumber(data.sales_stats.avg_monthly_quantity)} suffix="шт." Icon={Activity} />
                <StatCard label="Общая выручка" value={formatCurrency(data.sales_stats.total_revenue)} Icon={TrendingUp} />
            </div>

            <div style={{ backgroundColor: 'var(--surface-soft)', borderRadius: '10px', padding: '18px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)' }}>Сезонные показатели</div>

                {data.peaks.length > 0 && (
                    <div>
                        <div style={labelStyle}><TrendingUp style={{ width: 11, height: 11, color: '#3a7c4a' }} /> Пики продаж</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {data.peaks.map((p, i) => <PeakTag key={i} label={`${p.month}: +${p.deviation_percent.toFixed(1)}%`} deviation={p.deviation_percent} isHigh />)}
                        </div>
                    </div>
                )}

                {data.troughs.length > 0 && (
                    <div>
                        <div style={labelStyle}><TrendingDown style={{ width: 11, height: 11, color: '#a03a3a' }} /> Спады продаж</div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                            {data.troughs.map((t, i) => <PeakTag key={i} label={`${t.month}: ${t.deviation_percent.toFixed(1)}%`} deviation={t.deviation_percent} isHigh={false} />)}
                        </div>
                    </div>
                )}

                <div>
                    <div style={labelStyle}><Clock style={{ width: 11, height: 11 }} /> Метрики стабильности</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '10px' }}>
                        <div style={{ backgroundColor: 'var(--canvas)', borderRadius: '8px', padding: '12px 14px' }}>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Стандартное отклонение</div>
                            <div style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{data.stability_metrics.coefficient_std.toFixed(2)}</div>
                        </div>
                        <div style={{ backgroundColor: 'var(--canvas)', borderRadius: '8px', padding: '12px 14px' }}>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', marginBottom: '4px' }}>Макс. отклонение</div>
                            <div style={{ fontFamily: 'var(--serif)', fontSize: '18px', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{(data.stability_metrics.max_deviation * 100).toFixed(1)}%</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

StatCard.propTypes = { label: PropTypes.string, value: PropTypes.oneOfType([PropTypes.string, PropTypes.number]), suffix: PropTypes.string, Icon: PropTypes.elementType };
PeakTag.propTypes = { label: PropTypes.string, deviation: PropTypes.number, isHigh: PropTypes.bool };

SeasonalStatistics.propTypes = {
    data: PropTypes.shape({
        name: PropTypes.string,
        article: PropTypes.string,
        sales_stats: PropTypes.shape({ avg_monthly_quantity: PropTypes.number, total_revenue: PropTypes.number }),
        peaks: PropTypes.arrayOf(PropTypes.shape({ month: PropTypes.string, deviation_percent: PropTypes.number })),
        troughs: PropTypes.arrayOf(PropTypes.shape({ month: PropTypes.string, deviation_percent: PropTypes.number })),
        stability_metrics: PropTypes.shape({ coefficient_std: PropTypes.number, max_deviation: PropTypes.number }),
    }),
};

export default SeasonalStatistics;
