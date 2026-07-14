import PropTypes from 'prop-types';
import { StatisticsPropTypes } from './types';
import StatCard from '../../ui/StatCard';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

const SupplierStatistics = ({ stats }) => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12, marginBottom: 20 }}>
        <StatCard title="Поставщики" value={fmt(stats.total_suppliers)} />
        <StatCard title="Приёмки" value={fmt(stats.total_supplies)} />
        <StatCard title="Позиции" value={fmt(stats.total_positions)} />
        <StatCard title="Общая сумма" value={`${fmt(stats.total_sum)} ₽`} />
    </div>
);

SupplierStatistics.propTypes = {
    stats: PropTypes.shape(StatisticsPropTypes).isRequired,
};

export default SupplierStatistics;
