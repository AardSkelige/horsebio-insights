import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { DateRange, ResetFilters, SearchInput, Select, Toolbar } from '../../ui';
import { suppliesApi } from '../../../api/suppliesApi';

const EMPTY = { search: '', group: '', startDate: null, endDate: null };

const MaterialSupplyFilterPanel = ({ filters, onChange }) => {
    const [groups, setGroups] = useState([]);

    useEffect(() => {
        suppliesApi.materials.getAll()
            .then((data) => {
                if (data.status !== 'success') return;
                setGroups(data.data.available_groups.filter(Boolean));
            })
            .catch(() => {});
    }, []);

    const hasFilters = Boolean(filters.search || filters.group || filters.startDate || filters.endDate);

    return (
        <Toolbar>
            <SearchInput
                value={filters.search}
                onChange={(search) => onChange({ ...filters, search })}
                placeholder="Поиск материала"
            />

            <Select
                value={filters.group || ''}
                placeholder="Все группы"
                options={groups}
                onChange={(e) => onChange({ ...filters, group: e.target.value })}
                aria-label="Группа"
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

MaterialSupplyFilterPanel.propTypes = {
    filters: PropTypes.shape({
        search: PropTypes.string,
        group: PropTypes.string,
        startDate: PropTypes.string,
        endDate: PropTypes.string,
    }).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default MaterialSupplyFilterPanel;
