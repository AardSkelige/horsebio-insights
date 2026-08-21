import PropTypes from 'prop-types';
import { DateRange, ResetFilters, SearchInput, Toolbar } from '../../ui';

const EMPTY = { search: '', startDate: null, endDate: null };

const SupplierFilterPanel = ({ filters, onChange }) => {
    const hasFilters = Boolean(filters.search || filters.startDate || filters.endDate);

    return (
        <Toolbar>
            <SearchInput
                value={filters.search}
                onChange={(search) => onChange({ ...filters, search })}
                placeholder="Поиск поставщика"
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

SupplierFilterPanel.propTypes = {
    filters: PropTypes.shape({
        search: PropTypes.string,
        startDate: PropTypes.string,
        endDate: PropTypes.string,
    }).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default SupplierFilterPanel;
