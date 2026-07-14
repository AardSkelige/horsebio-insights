import PropTypes from 'prop-types';

export const ProductPropTypes = {
    id: PropTypes.number,
    name: PropTypes.string,
    group: PropTypes.string,
    subgroup: PropTypes.string,
    quantity: PropTypes.number,
    average_price: PropTypes.number,
    total_sum: PropTypes.number,
    shipments_count: PropTypes.number
};

export const FiltersPropTypes = {
    search: PropTypes.string,
    subgroup: PropTypes.string,
    startDate: PropTypes.string,
    endDate: PropTypes.string,
};

export const StatisticsPropTypes = {
    total_products: PropTypes.number,
    total_shipments: PropTypes.number,
    top_by_quantity: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        quantity: PropTypes.number,
        shipments_count: PropTypes.number
    })),
    top_by_revenue: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        revenue: PropTypes.number,
        price_per_unit: PropTypes.number
    })),
    top_by_average_quantity: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        average_quantity: PropTypes.string
    }))
};

export const ProductDetailsPropTypes = {
    product: PropTypes.shape({
        id: PropTypes.number,
        name: PropTypes.string,
        group: PropTypes.string,
        subgroup: PropTypes.string
    }),
    statistics: PropTypes.shape({
        total_shipments: PropTypes.number,
        total_quantity: PropTypes.number,
        average_quantity: PropTypes.number,
        total_revenue: PropTypes.number,
        price_range: PropTypes.shape({ min: PropTypes.number, max: PropTypes.number })
    }),
    materials: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string,
        quantity: PropTypes.number,
        unit: PropTypes.string
    })),
    shipments_history: PropTypes.arrayOf(PropTypes.shape({
        number: PropTypes.string,
        date: PropTypes.string,
        quantity: PropTypes.number,
        price: PropTypes.number,
        total: PropTypes.number
    })),
    monthly_dynamics: PropTypes.arrayOf(PropTypes.shape({
        month: PropTypes.string,
        quantity: PropTypes.number,
        revenue: PropTypes.number
    }))
};
