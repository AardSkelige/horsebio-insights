import PropTypes from 'prop-types';
import { num } from '../../../../utils/formatters';
import { StatCard, StatGrid } from '../../../ui';


const StatisticsSection = ({ statistics }) => (
    <StatGrid>
        <StatCard title="Общая сумма"      value={`${num(statistics.total_sum)} ₽`} />
        <StatCard title="Позиций"          value={num(statistics.positions_count)} />
        <StatCard title="Уникальных материалов" value={num(statistics.unique_materials)} />
        <StatCard title="Средняя сумма"    value={`${num(statistics.avg_supply_sum)} ₽`} />
    </StatGrid>
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
