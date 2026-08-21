import PropTypes from 'prop-types';
import { num } from '../../../utils/formatters';
import { StatCard, StatGrid } from '../../ui';
import { StatisticsPropTypes } from './types';


const SupplierStatistics = ({ stats }) => (
    <StatGrid>
        <StatCard title="Поставщики" value={num(stats.total_suppliers)} />
        <StatCard title="Приёмки" value={num(stats.total_supplies)} />
        <StatCard title="Позиции" value={num(stats.total_positions)} />
        <StatCard title="Общая сумма" value={`${num(stats.total_sum)} ₽`} />
    </StatGrid>
);

SupplierStatistics.propTypes = {
    stats: PropTypes.shape(StatisticsPropTypes).isRequired,
};

export default SupplierStatistics;
