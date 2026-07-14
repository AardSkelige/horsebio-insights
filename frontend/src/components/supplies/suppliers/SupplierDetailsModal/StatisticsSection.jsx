import PropTypes from 'prop-types';
import StatCard from '../../../ui/StatCard';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

const StatisticsSection = ({ statistics }) => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
        <StatCard size={24} title="Общая сумма"      value={`${fmt(statistics.total_sum)} ₽`} />
        <StatCard size={24} title="Позиций"          value={fmt(statistics.positions_count)} />
        <StatCard size={24} title="Уникальных материалов" value={fmt(statistics.unique_materials)} />
        <StatCard size={24} title="Средняя сумма"    value={`${fmt(statistics.avg_supply_sum)} ₽`} />
    </div>
);

StatisticsSection.propTypes = {
    statistics: PropTypes.shape({
        total_sum: PropTypes.number.isRequired,
        positions_count: PropTypes.number.isRequired,
        unique_materials: PropTypes.number.isRequired,
        avg_supply_sum: PropTypes.number.isRequired,
    }).isRequired,
};

export default StatisticsSection;
