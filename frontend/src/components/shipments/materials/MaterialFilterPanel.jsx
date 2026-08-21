import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { FiltersPropTypes } from './types';
import { DateRange, MultiSelect, ResetFilters, SearchInput, Select, Toolbar } from '../../ui';
import { materialsApi } from '../../../api/materialsApi';

const EMPTY = { search: '', group: '', counterparties: [], startDate: null, endDate: null };

const MaterialFilterPanel = ({ filters, onChange }) => {
    const [groups, setGroups] = useState([]);
    const [counterparties, setCounterparties] = useState([]);

    useEffect(() => {
        materialsApi.getAll()
            .then((data) => {
                if (data.status !== 'success') return;
                setGroups(data.data.available_groups.filter(Boolean));
                setCounterparties(data.data.counterparties.map((c) => ({ label: c.name, value: c.id.toString() })));
            })
            .catch(() => {});
    }, []);

    const hasFilters = Boolean(
        filters.search || filters.group || filters.counterparties.length || filters.startDate || filters.endDate,
    );

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

            <MultiSelect
                options={counterparties}
                value={filters.counterparties}
                onChange={(v) => onChange({ ...filters, counterparties: v })}
                placeholder="Контрагенты"
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

MaterialFilterPanel.propTypes = {
    filters: PropTypes.shape(FiltersPropTypes).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default MaterialFilterPanel;
