import PropTypes from 'prop-types';
import { StatCard, StatGrid } from '../../ui';
import { StatisticsPropTypes } from './types';


const CounterpartyStatistics = ({ stats }) => (
    <StatGrid>
        <StatCard title="Всего контрагентов" value={stats.total_counterparties} note="активных контрагентов" />
        <StatCard title="Всего отгрузок"     value={stats.total_shipments}      note="выполненных отгрузок" />
        <StatCard title="Всего товаров"       value={stats.total_products}       note="наименований товаров" />
    </StatGrid>
);

CounterpartyStatistics.propTypes = {
    stats: PropTypes.shape(StatisticsPropTypes).isRequired,
};

export default CounterpartyStatistics;
