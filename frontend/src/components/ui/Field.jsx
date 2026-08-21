import { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { Check, ChevronDown, Search, X } from 'lucide-react';

/**
 * Поле ввода. Заменяет константу `inputStyle`, которая была скопирована
 * в шесть десятков компонентов.
 */
export function Input({ block = false, className = '', ...rest }) {
    const classes = ['ui-input', block ? 'ui-input--block' : '', className]
        .filter(Boolean).join(' ');
    return <input className={classes} {...rest} />;
}

Input.propTypes = {
    block: PropTypes.bool,
    className: PropTypes.string,
};

/**
 * Выпадающий список.
 *
 * Системная стрелка скрыта и нарисована своя: нативная в Safari и Chrome
 * выглядит по-разному и не следует теме. Плейсхолдер (пустое значение)
 * показывается приглушённым — как в поле ввода.
 */
export function Select({ value, placeholder, options = [], className = '', children, ...rest }) {
    return (
        <div className={['ui-select', className].filter(Boolean).join(' ')}>
            <select
                className={`ui-input ui-select__control${value ? '' : ' is-placeholder'}`}
                value={value}
                {...rest}
            >
                {placeholder !== undefined && <option value="">{placeholder}</option>}
                {options.map((o) => {
                    const val = typeof o === 'string' ? o : o.value;
                    const label = typeof o === 'string' ? o : o.label;
                    return <option key={val} value={val}>{label}</option>;
                })}
                {children}
            </select>
            <ChevronDown size={12} className="ui-select__chevron" aria-hidden="true" />
        </div>
    );
}

Select.propTypes = {
    value: PropTypes.string,
    placeholder: PropTypes.string,
    options: PropTypes.arrayOf(PropTypes.oneOfType([
        PropTypes.string,
        PropTypes.shape({ label: PropTypes.string, value: PropTypes.string }),
    ])),
    className: PropTypes.string,
    children: PropTypes.node,
};

/**
 * Поиск: иконка слева, крестик очистки справа.
 *
 * Крестик появляется только при непустом значении — пустая кнопка очистки
 * сбивает с толку, поэтому её не показываем вовсе.
 */
export function SearchInput({ value, onChange, placeholder = 'Поиск', className = '', ...rest }) {
    return (
        <div className={['ui-search', className].filter(Boolean).join(' ')}>
            <span className="ui-search__icon">
                <Search size={13} aria-hidden="true" />
            </span>
            <input
                className="ui-input ui-search__input"
                placeholder={placeholder}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                {...rest}
            />
            {value && (
                <button
                    type="button"
                    className="ui-search__clear"
                    onClick={() => onChange('')}
                    aria-label="Очистить поиск"
                >
                    <X size={12} aria-hidden="true" />
                </button>
            )}
        </div>
    );
}

SearchInput.propTypes = {
    value: PropTypes.string,
    onChange: PropTypes.func.isRequired,
    placeholder: PropTypes.string,
    className: PropTypes.string,
};

/**
 * Множественный выбор с поиском по вариантам.
 *
 * Нативный `<select multiple>` в списке из сотен контрагентов бесполезен,
 * поэтому список свой: чекбоксы, поиск и кнопка сброса.
 */
export function MultiSelect({
    options, value, onChange, placeholder,
    searchPlaceholder = 'Поиск...',
    formatSelected = (n) => `Выбрано: ${n}`,
    block = false,
}) {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const ref = useRef(null);

    useEffect(() => {
        if (!open) return undefined;
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    // Ищем и по подписи, и по вспомогательной метке — у материалов это код
    const q = search.toLowerCase();
    const filtered = options.filter(
        (o) => o.label.toLowerCase().includes(q) || (o.hint || '').toLowerCase().includes(q),
    );
    const toggle = (val) => {
        onChange(value.includes(val) ? value.filter((v) => v !== val) : [...value, val]);
    };

    return (
        <div ref={ref} className={`ui-multiselect${block ? ' is-block' : ''}`}>
            <button
                type="button"
                className="ui-input ui-multiselect__control"
                onClick={() => setOpen((o) => !o)}
                aria-expanded={open}
            >
                <span className={value.length ? undefined : 'ui-multiselect__placeholder'}>
                    {value.length ? formatSelected(value.length) : placeholder}
                </span>
                <ChevronDown size={12} className={`ui-select__chevron is-static${open ? ' is-open' : ''}`} aria-hidden="true" />
            </button>

            {open && (
                <div className="ui-multiselect__menu">
                    <div className="ui-multiselect__search">
                        <SearchInput value={search} onChange={setSearch} placeholder={searchPlaceholder} autoFocus />
                    </div>

                    <div className="ui-multiselect__list">
                        {filtered.length === 0 ? (
                            <div className="ui-multiselect__empty">Ничего не найдено</div>
                        ) : filtered.map((o) => {
                            const checked = value.includes(o.value);
                            return (
                                <label key={o.value} className={`ui-multiselect__option${checked ? ' is-checked' : ''}`}>
                                    <input
                                        type="checkbox"
                                        checked={checked}
                                        onChange={() => toggle(o.value)}
                                        className="ui-multiselect__native"
                                    />
                                    <span className="ui-multiselect__box" aria-hidden="true">
                                        {checked && <Check size={9} />}
                                    </span>
                                    <span className="ui-multiselect__label">{o.label}</span>
                                    {o.hint && <span className="ui-multiselect__hint">{o.hint}</span>}
                                </label>
                            );
                        })}
                    </div>

                    {value.length > 0 && (
                        <div className="ui-multiselect__footer">
                            <button
                                type="button"
                                className="ui-btn ui-btn--quiet ui-btn--sm"
                                onClick={() => { onChange([]); setOpen(false); }}
                            >
                                Сбросить выбор
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

MultiSelect.propTypes = {
    options: PropTypes.arrayOf(PropTypes.shape({
        label: PropTypes.string,
        value: PropTypes.string,
        hint: PropTypes.string,
    })).isRequired,
    value: PropTypes.arrayOf(PropTypes.string).isRequired,
    onChange: PropTypes.func.isRequired,
    placeholder: PropTypes.string.isRequired,
    searchPlaceholder: PropTypes.string,
    formatSelected: PropTypes.func,
    block: PropTypes.bool,
};

/**
 * Диапазон дат. Классы `filter-date-range` описаны в `index.css` — на узком
 * экране пара полей разворачивается в столбик, а тире между ними прячется.
 */
export function DateRange({ from, to, onChange }) {
    return (
        <div className="filter-date-range">
            <Input
                type="date"
                value={from || ''}
                onChange={(e) => onChange({ from: e.target.value || null, to })}
                aria-label="Дата начала"
            />
            <span className="filter-date-sep ui-date-sep">—</span>
            <Input
                type="date"
                value={to || ''}
                min={from || undefined}
                onChange={(e) => onChange({ from, to: e.target.value || null })}
                aria-label="Дата окончания"
            />
        </div>
    );
}

DateRange.propTypes = {
    from: PropTypes.string,
    to: PropTypes.string,
    onChange: PropTypes.func.isRequired,
};

/**
 * Кнопка сброса фильтров. Появляется только когда есть что сбрасывать —
 * поэтому во всех панелях рядом с ней стоял один и тот же признак `hasFilters`.
 */
export function ResetFilters({ onReset, children = 'Сбросить' }) {
    return (
        <button type="button" className="ui-btn ui-btn--ghost ui-btn--md ui-reset" onClick={onReset}>
            <X size={12} aria-hidden="true" />
            {children}
        </button>
    );
}

ResetFilters.propTypes = {
    onReset: PropTypes.func.isRequired,
    children: PropTypes.node,
};
