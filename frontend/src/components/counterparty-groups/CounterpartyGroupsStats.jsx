import PropTypes from 'prop-types';
import { formatNumber, formatCurrency } from '../../utils/formatters';

const COLORS = {
    large:      'var(--primary)',
    medium:     'var(--info)',
    small:      'var(--success)',
    rare_large: 'var(--cat-clay)',
};

const CATEGORY_NAMES = {
    large:      'Крупные (регулярные)',
    medium:     'Средние (регулярные)',
    small:      'Мелкие (нерегулярные)',
    rare_large: 'Крупные (редкие)',
};



export const CounterpartyGroupsStats = ({ data }) => {
    if (!data?.categories) return null;

    const totalCounterparties = Object.values(data.categories).reduce((s, c) => s + c.counterparties_count, 0);
    const totalVolume = Object.values(data.categories).reduce((s, c) => s + c.total_monthly_volume, 0);

    const rows = Object.entries(data.categories).map(([key, cat]) => ({
        key,
        name: CATEGORY_NAMES[key],
        color: COLORS[key],
        count: cat.counterparties_count,
        countShare: totalCounterparties ? ((cat.counterparties_count / totalCounterparties) * 100).toFixed(1) : '0.0',
        volume: cat.total_monthly_volume,
        volumeShare: totalVolume ? cat.total_monthly_volume / totalVolume : 0,
        frequency: cat.avg_frequency,
    }));

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ overflowX: 'auto' }}>
                <table className="ui-table">
                    <thead>
                        <tr>
                            <th>Группа</th>
                            <th>Контрагенты</th>
                            <th style={{ minWidth: '220px' }}>Объём продаж</th>
                            <th>Активность</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map(r => (
                            <tr key={r.key}>
                                <td>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                        <span style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: r.color, flexShrink: 0 }} />
                                        <span style={{ fontWeight: 500, color: 'var(--ink)' }}>{r.name}</span>
                                    </div>
                                </td>
                                <td>
                                    <div style={{ fontWeight: 500 }}>{formatNumber(r.count)}</div>
                                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{r.countShare}% от общего</div>
                                </td>
                                <td>
                                    <div style={{ fontWeight: 500, marginBottom: '6px' }}>{formatCurrency(r.volume)}</div>
                                    <div style={{ height: 4, borderRadius: 2, backgroundColor: 'var(--surface-cream-strong)', overflow: 'hidden', marginBottom: '4px' }}>
                                        <div style={{ height: '100%', borderRadius: 2, backgroundColor: r.color, width: `${(r.volumeShare * 100).toFixed(1)}%`, transition: 'width 400ms ease' }} />
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{(r.volumeShare * 100).toFixed(1)}% от общего объёма</div>
                                </td>
                                <td>
                                    <div style={{ fontWeight: 500 }}>{(r.frequency * 100).toFixed(1)}%</div>
                                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>частота заказов</div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', backgroundColor: 'var(--surface-soft)', padding: '12px 14px', borderRadius: '8px', lineHeight: 1.7 }}>
                Объём продаж — среднемесячный показатель за выбранный период · Активность — % месяцев с заказами · Прогресс-бар — доля группы в общем объёме
            </div>
        </div>
    );
};

CounterpartyGroupsStats.propTypes = {
    data: PropTypes.shape({
        categories: PropTypes.objectOf(PropTypes.shape({
            counterparties_count: PropTypes.number.isRequired,
            total_monthly_volume: PropTypes.number.isRequired,
            avg_frequency: PropTypes.number.isRequired,
        })).isRequired,
    }).isRequired,
};

export default CounterpartyGroupsStats;
