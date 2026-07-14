import PropTypes from 'prop-types';

const selectStyle = {
    height: '36px', padding: '0 10px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '8px', outline: 'none', cursor: 'pointer', width: '100%',
};

const dateStyle = {
    height: '36px', padding: '0 10px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '8px', outline: 'none', width: '100%',
};

const fieldStyle = { display: 'flex', flexDirection: 'column', gap: '4px', flex: '1 1 200px', minWidth: 0 };
const labelStyle = { fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', letterSpacing: '0.04em' };
const hintStyle = { fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' };

export const CounterpartyGroupsFilters = ({ value, onChange }) => (
    <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
        <div style={fieldStyle}>
            <label style={labelStyle}>Период анализа</label>
            <select
                value={value.periodMonths}
                onChange={e => onChange({ ...value, periodMonths: Number(e.target.value) })}
                style={selectStyle}
                onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                onBlur={e => e.target.style.borderColor = 'var(--hairline)'}
            >
                <option value={3}>3 месяца</option>
                <option value={6}>6 месяцев</option>
                <option value={12}>12 месяцев</option>
            </select>
            <span style={hintStyle}>Глубина анализа клиентской базы</span>
        </div>
        <div style={fieldStyle}>
            <label style={labelStyle}>Дата окончания</label>
            <input
                type="date"
                value={value.endDate || ''}
                onChange={e => onChange({ ...value, endDate: e.target.value || null })}
                style={dateStyle}
                onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                onBlur={e => e.target.style.borderColor = 'var(--hairline)'}
            />
            <span style={hintStyle}>По умолчанию — текущая дата</span>
        </div>
    </div>
);

CounterpartyGroupsFilters.propTypes = {
    value: PropTypes.shape({
        periodMonths: PropTypes.number.isRequired,
        endDate: PropTypes.string
    }).isRequired,
    onChange: PropTypes.func.isRequired
};

export default CounterpartyGroupsFilters;
