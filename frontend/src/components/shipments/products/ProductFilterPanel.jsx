import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { FiltersPropTypes } from './types';
import { DateRange, ResetFilters, SearchInput, Select, Toolbar } from '../../ui';
import { productsApi } from '../../../api/productsApi';

const EMPTY = { search: '', subgroup: '', salesChannel: '', startDate: null, endDate: null };

const ProductFilterPanel = ({ filters, onChange }) => {
    const [subgroups, setSubgroups] = useState([]);
    const [salesChannels, setSalesChannels] = useState([]);

    useEffect(() => {
        productsApi.getAll()
            .then((data) => {
                if (data.status !== 'success') return;
                setSubgroups(data.data.available_subgroups.filter(Boolean));
                setSalesChannels((data.data.available_sales_channels || []).filter(Boolean));
            })
            .catch(() => {});
    }, []);

    const hasFilters = Boolean(
        filters.search || filters.subgroup || filters.salesChannel || filters.startDate || filters.endDate
    );

    return (
        <Toolbar>
            <SearchInput
                value={filters.search}
                onChange={(search) => onChange({ ...filters, search })}
                placeholder="Поиск товара"
            />

            <Select
                value={filters.subgroup || ''}
                placeholder="Все подгруппы"
                options={subgroups}
                onChange={(e) => onChange({ ...filters, subgroup: e.target.value })}
                aria-label="Подгруппа"
            />

            <Select
                value={filters.salesChannel || ''}
                placeholder="Все каналы продаж"
                options={salesChannels}
                onChange={(e) => onChange({ ...filters, salesChannel: e.target.value })}
                aria-label="Канал продаж"
            />

            <DateRange
                from={filters.startDate}
                to={filters.endDate}
                onChange={({ from, to }) => onChange({ ...filters, startDate: from, endDate: to })}
            />

            {hasFilters && <ResetFilters onReset={() => onChange(EMPTY)} />}
        </Toolbar>
    );
};

ProductFilterPanel.propTypes = {
    filters: PropTypes.shape(FiltersPropTypes).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default ProductFilterPanel;
