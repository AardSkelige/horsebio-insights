import PropTypes from 'prop-types';

export const MaterialPropTypes = {
    id: PropTypes.number,
    name: PropTypes.string,
    code: PropTypes.string,
    group: PropTypes.string,
    uom: PropTypes.string,
    total_usage: PropTypes.number,
    shipments_count: PropTypes.number,
    suppliers_count: PropTypes.number,
};

export const FiltersPropTypes = {
    search: PropTypes.string,
    group: PropTypes.string,
    counterparties: PropTypes.arrayOf(PropTypes.string),
    startDate: PropTypes.string,
    endDate: PropTypes.string,
};
