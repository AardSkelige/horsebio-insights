import { useEffect, useState, useRef } from 'react';
import PropTypes from 'prop-types';
import { Search, X, ChevronDown, Check } from 'lucide-react';
import { FiltersPropTypes } from './types';
import { materialsApi } from '../../../api/materialsApi';

const inputStyle = {
    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)',
    background: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: 8, padding: '7px 12px', outline: 'none',
};

/* Нативный мульти-селект с поиском */
const MultiSelect = ({ options, value, onChange, placeholder }) => {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const ref = useRef(null);

    useEffect(() => {
        const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const filtered = options.filter(o => o.label.toLowerCase().includes(search.toLowerCase()));
    const toggle = (val) => {
        const next = value.includes(val) ? value.filter(v => v !== val) : [...value, val];
        onChange(next);
    };

    return (
        <div ref={ref} style={{ position: 'relative', flex: '1 1 200px' }}>
            <button
                type="button"
                onClick={() => setOpen(o => !o)}
                style={{ ...inputStyle, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', width: '100%', justifyContent: 'space-between', boxSizing: 'border-box' }}
            >
                <span style={{ color: value.length ? 'var(--ink)' : 'var(--muted)' }}>
                    {value.length ? `Выбрано: ${value.length}` : placeholder}
                </span>
                <ChevronDown size={12} style={{ color: 'var(--muted)', flexShrink: 0, transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />
            </button>

            {open && (
                <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, zIndex: 100, background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, boxShadow: '0 4px 16px rgba(20,20,19,0.1)', minWidth: 260, maxHeight: 280, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--hairline)' }}>
                        <div style={{ position: 'relative' }}>
                            <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
                            <input
                                autoFocus
                                style={{ ...inputStyle, paddingLeft: 26, width: '100%', boxSizing: 'border-box', fontSize: 12 }}
                                placeholder="Поиск..."
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                            />
                        </div>
                    </div>
                    <div style={{ overflowY: 'auto', maxHeight: 220 }}>
                        {filtered.length === 0 ? (
                            <div style={{ padding: '12px 14px', fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Ничего не найдено</div>
                        ) : filtered.map(o => (
                            <div
                                key={o.value}
                                onClick={() => toggle(o.value)}
                                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)', background: value.includes(o.value) ? 'var(--surface-soft)' : 'transparent' }}
                                onMouseEnter={e => { if (!value.includes(o.value)) e.currentTarget.style.background = 'var(--surface-soft)'; }}
                                onMouseLeave={e => { if (!value.includes(o.value)) e.currentTarget.style.background = 'transparent'; }}
                            >
                                <div style={{ width: 14, height: 14, borderRadius: 3, border: `1px solid ${value.includes(o.value) ? 'var(--primary)' : 'var(--hairline)'}`, background: value.includes(o.value) ? 'var(--primary)' : 'transparent', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    {value.includes(o.value) && <Check size={9} style={{ color: '#fff' }} />}
                                </div>
                                {o.label}
                            </div>
                        ))}
                    </div>
                    {value.length > 0 && (
                        <div style={{ padding: '6px 10px', borderTop: '1px solid var(--hairline)' }}>
                            <button onClick={() => { onChange([]); setOpen(false); }} style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                                Сбросить выбор
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

MultiSelect.propTypes = {
    options: PropTypes.arrayOf(PropTypes.shape({ label: PropTypes.string, value: PropTypes.string })).isRequired,
    value: PropTypes.arrayOf(PropTypes.string).isRequired,
    onChange: PropTypes.func.isRequired,
    placeholder: PropTypes.string.isRequired,
};

/* Основной фильтр */
const MaterialFilterPanel = ({ filters, onChange }) => {
    const [groups, setGroups] = useState([]);
    const [counterparties, setCounterparties] = useState([]);

    useEffect(() => {
        materialsApi.getAll()
            .then(data => {
                if (data.status !== 'success') return;
                setGroups(data.data.available_groups.filter(Boolean).map(g => ({ label: g, value: g })));
                setCounterparties(data.data.counterparties.map(c => ({ label: c.name, value: c.id.toString() })));
            })
            .catch(() => {});
    }, []);

    const hasFilters = filters.search || filters.group || filters.counterparties.length || filters.startDate || filters.endDate;

    return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginBottom: 16 }}>
            {/* Поиск */}
            <div style={{ position: 'relative', flex: '1 1 200px' }}>
                <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
                <input
                    style={{ ...inputStyle, paddingLeft: 30, width: '100%', boxSizing: 'border-box' }}
                    placeholder="Поиск материала"
                    value={filters.search}
                    onChange={e => onChange({ ...filters, search: e.target.value })}
                />
                {filters.search && (
                    <button onClick={() => onChange({ ...filters, search: '' })}
                        style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}>
                        <X size={12} />
                    </button>
                )}
            </div>

            {/* Группа */}
            <div style={{ position: 'relative', flex: '1 1 140px' }}>
                <select
                    style={{ ...inputStyle, cursor: 'pointer', paddingRight: 36, width: '100%', boxSizing: 'border-box', appearance: 'none', WebkitAppearance: 'none', color: filters.group ? 'var(--ink)' : 'var(--muted)' }}
                    value={filters.group || ''}
                    onChange={e => onChange({ ...filters, group: e.target.value || '' })}
                >
                    <option value="">Все группы</option>
                    {groups.map(g => <option key={g.value} value={g.value}>{g.label}</option>)}
                </select>
                <ChevronDown size={12} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
            </div>

            {/* Контрагенты */}
            <MultiSelect
                options={counterparties}
                value={filters.counterparties}
                onChange={v => onChange({ ...filters, counterparties: v })}
                placeholder="Контрагенты"
            />

            {/* Даты */}
            <div className="filter-date-range">
                <input type="date" style={inputStyle}
                    value={filters.startDate || ''}
                    onChange={e => onChange({ ...filters, startDate: e.target.value || null })}
                />
                <span className="filter-date-sep" style={{ fontSize: 12, color: 'var(--muted)', flexShrink: 0, lineHeight: 1 }}>—</span>
                <input type="date" style={inputStyle}
                    value={filters.endDate || ''}
                    min={filters.startDate || undefined}
                    onChange={e => onChange({ ...filters, endDate: e.target.value || null })}
                />
            </div>

            {/* Сброс */}
            {hasFilters && (
                <button
                    onClick={() => onChange({ search: '', group: '', counterparties: [], startDate: null, endDate: null })}
                    style={{ ...inputStyle, display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', color: 'var(--muted)', padding: '7px 10px' }}
                >
                    <X size={12} /> Сбросить
                </button>
            )}
        </div>
    );
};

MaterialFilterPanel.propTypes = {
    filters: PropTypes.shape(FiltersPropTypes).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default MaterialFilterPanel;
