import PropTypes from 'prop-types';
import { StatCard, StatGrid } from '../../ui';


const MaterialStatistics = ({ stats }) => (
    <StatGrid>
        <StatCard title="Материалы для производства" value={stats['Материалы для производства']} note="позиций материалов" />
        <StatCard title="Тара"      value={stats['Тара']}      note="видов тары" />
        <StatCard title="Этикетки"  value={stats['Этикетки']}  note="наименований этикеток" />
    </StatGrid>
);

MaterialStatistics.propTypes = {
    stats: PropTypes.shape({
        'Материалы для производства': PropTypes.number.isRequired,
        'Тара': PropTypes.number.isRequired,
        'Этикетки': PropTypes.number.isRequired,
    }).isRequired,
};

export default MaterialStatistics;
