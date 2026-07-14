// src/components/supplies/materials/types.js

import PropTypes from 'prop-types';

// Типы для материала
export const MaterialPropTypes = {
    id: PropTypes.number,
    name: PropTypes.string,
    code: PropTypes.string,
    group: PropTypes.string,
    uom: PropTypes.string,
    total_quantity: PropTypes.number,
    average_price: PropTypes.number,
    total_sum: PropTypes.number,
    supplies_count: PropTypes.number,
    suppliers_count: PropTypes.number
};

// Типы для фильтров
export const FiltersPropTypes = {
    search: PropTypes.string,
    group: PropTypes.string,
    startDate: PropTypes.object,
    endDate: PropTypes.object
};

// Типы для статистики
export const StatisticsPropTypes = {
    total_materials: PropTypes.number,
    total_supplies: PropTypes.number,
    total_suppliers: PropTypes.number,
    total_sum: PropTypes.number
};

// Типы для детальной информации
export const MaterialDetailsPropTypes = {
    material: PropTypes.shape({
        id: PropTypes.number,
        name: PropTypes.string,
        code: PropTypes.string,
        group: PropTypes.string,
        uom: PropTypes.string
    }),
    statistics: PropTypes.shape({
        total_supplies: PropTypes.number,
        total_quantity: PropTypes.number,
        total_sum: PropTypes.number,
        price_range: PropTypes.shape({
            min: PropTypes.number,
            max: PropTypes.number,
            avg: PropTypes.number
        })
    }),
    monthly_data: PropTypes.arrayOf(PropTypes.shape({
        month: PropTypes.string,
        quantity: PropTypes.number,
        avg_price: PropTypes.number
    })),
    supply_history: PropTypes.arrayOf(PropTypes.shape({
        number: PropTypes.string,
        date: PropTypes.string,
        supplier: PropTypes.string,
        quantity: PropTypes.number,
        price: PropTypes.number,
        total: PropTypes.number
    }))
};