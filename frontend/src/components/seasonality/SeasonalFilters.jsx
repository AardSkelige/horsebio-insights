import PropTypes from 'prop-types';
import { DateInput, FormField, Select } from '../ui';
import { ANALYSIS_PERIODS } from '../common/analysisPeriods';

const CATEGORIES = [
    { value: 'A', label: 'Категория A (топ-продукты)' },
    { value: 'B', label: 'Категория B (средние продукты)' },
    { value: 'C', label: 'Категория C (редкие продукты)' },
];

export const SeasonalFilters = ({ value, onChange }) => (
    <div className="ui-form-row">
        <FormField label="Категория продуктов">
            <Select value={value.category} options={CATEGORIES} onChange={e => onChange?.({ ...value, category: e.target.value })} />
        </FormField>
        <FormField label="Период анализа" hint="Для точной сезонности рекомендуется 12 мес.">
            <Select
                value={String(value.periodMonths)}
                options={ANALYSIS_PERIODS}
                onChange={e => onChange?.({ ...value, periodMonths: Number(e.target.value) })}
            />
        </FormField>
        <FormField label="Дата окончания" hint="По умолчанию — текущая дата">
            <DateInput placeholder="Сегодня" value={value.endDate || ''} onChange={e => onChange?.({ ...value, endDate: e.target.value || null })} />
        </FormField>
    </div>
);

SeasonalFilters.propTypes = {
    value: PropTypes.shape({
        category: PropTypes.string.isRequired,
        periodMonths: PropTypes.number.isRequired,
        endDate: PropTypes.string,
    }).isRequired,
    onChange: PropTypes.func,
};

export default SeasonalFilters;
