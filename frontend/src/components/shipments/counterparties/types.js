import PropTypes from 'prop-types';

export const CounterpartyPropTypes = {
    id: PropTypes.number,
    name: PropTypes.string,
    total_sales: PropTypes.number,
    shipments_count: PropTypes.number,
    total_products: PropTypes.number,
    last_shipment: PropTypes.string
};

export const FiltersPropTypes = {
    search: PropTypes.string,
    startDate: PropTypes.string,
    endDate: PropTypes.string
};

export const StatisticsPropTypes = {
    total_counterparties: PropTypes.number,
    total_shipments: PropTypes.number,
    total_products: PropTypes.number
};
