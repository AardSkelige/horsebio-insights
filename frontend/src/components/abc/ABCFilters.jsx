import PropTypes from 'prop-types';
import { DateInput, FormField, Select } from '../ui';
import { ANALYSIS_PERIODS } from '../common/analysisPeriods';

export const ABCFilters = ({ value, onChange }) => (
    <div className="ui-form-row">
        <FormField label="Период анализа" hint="Глубина исторических данных">
            <Select
                value={String(value.periodMonths)}
                options={ANALYSIS_PERIODS}
                onChange={e => onChange({ ...value, periodMonths: Number(e.target.value) })}
            />
        </FormField>
        <FormField label="Дата окончания" hint="По умолчанию — текущая дата">
            <DateInput placeholder="Сегодня" value={value.endDate || ''} onChange={e => onChange({ ...value, endDate: e.target.value || null })} />
        </FormField>
    </div>
);

ABCFilters.propTypes = {
    value: PropTypes.shape({
        periodMonths: PropTypes.number.isRequired,
        endDate: PropTypes.string,
    }).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default ABCFilters;
