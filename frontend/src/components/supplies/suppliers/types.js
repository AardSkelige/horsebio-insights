import PropTypes from 'prop-types';

export const SupplierPropTypes = {
    id: PropTypes.number,
    name: PropTypes.string,
    supplies_count: PropTypes.number,
    total_sum: PropTypes.number,
    positions_count: PropTypes.number,
    unique_materials: PropTypes.number,
    avg_supply_sum: PropTypes.number,
    last_supply: PropTypes.string
};

export const FiltersPropTypes = {
    search: PropTypes.string,
    startDate: PropTypes.string,
    endDate: PropTypes.string,
};

export const StatisticsPropTypes = {
    total_suppliers: PropTypes.number,
    total_supplies: PropTypes.number,
    total_positions: PropTypes.number,
    total_sum: PropTypes.number
};

export const SupplierDetailsPropTypes = {
    supplier: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
    statistics: PropTypes.shape({
        total_sum: PropTypes.number,
        positions_count: PropTypes.number,
        unique_materials: PropTypes.number,
        avg_supply_sum: PropTypes.number
    }),
    categories: PropTypes.objectOf(PropTypes.shape({
        materials: PropTypes.array,
        total_sum: PropTypes.number
    })),
    supply_history: PropTypes.array,
};
