import PropTypes from 'prop-types';
import { FiltersPropTypes } from './types';
import { DateRange, ResetFilters, SearchInput, Toolbar } from '../../ui';

const EMPTY = { search: '', startDate: null, endDate: null };

const CounterpartyFilterPanel = ({ filters, onChange }) => {
    const hasFilters = Boolean(filters.search || filters.startDate || filters.endDate);

    return (
        <Toolbar>
            <SearchInput
                value={filters.search}
                onChange={(search) => onChange({ ...filters, search })}
                placeholder="Поиск контрагента"
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

CounterpartyFilterPanel.propTypes = {
    filters: PropTypes.shape(FiltersPropTypes).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default CounterpartyFilterPanel;
