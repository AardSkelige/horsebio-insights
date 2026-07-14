import PropTypes from 'prop-types';
import { StatisticsPropTypes } from './types';

const StatCard = ({ title, count, description }) => (
    <div style={{
        background: 'var(--surface-card)',
        borderRadius: 12,
        padding: '16px 20px',
        border: '1px solid var(--hairline)',
    }}>
        <div style={{
            fontSize: 11, fontWeight: 500, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8,
            fontFamily: 'var(--sans)',
        }}>
            {title}
        </div>
        <div style={{
            fontFamily: 'var(--serif)', fontSize: 28, fontWeight: 400,
            letterSpacing: '-0.02em', lineHeight: 1, color: 'var(--ink)',
            fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
        }}>
            {count.toLocaleString('ru-RU')}
        </div>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
            {description}
        </div>
    </div>
);

StatCard.propTypes = {
    title: PropTypes.string.isRequired,
    count: PropTypes.number.isRequired,
    description: PropTypes.string.isRequired,
};

const CounterpartyStatistics = ({ stats }) => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
        <StatCard title="Всего контрагентов" count={stats.total_counterparties} description="активных контрагентов" />
        <StatCard title="Всего отгрузок"     count={stats.total_shipments}      description="выполненных отгрузок" />
        <StatCard title="Всего товаров"       count={stats.total_products}       description="наименований товаров" />
    </div>
);

CounterpartyStatistics.propTypes = {
    stats: PropTypes.shape(StatisticsPropTypes).isRequired,
};

export default CounterpartyStatistics;
