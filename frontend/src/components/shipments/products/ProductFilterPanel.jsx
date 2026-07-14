import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Search, X, ChevronDown } from 'lucide-react';
import { FiltersPropTypes } from './types';
import { productsApi } from '../../../api/productsApi';

const inputStyle = {
    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)',
    background: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: 8, padding: '7px 12px', outline: 'none',
};

const ProductFilterPanel = ({ filters, onChange }) => {
    const [subgroups, setSubgroups] = useState([]);

    useEffect(() => {
        productsApi.getAll()
            .then(data => {
                if (data.status !== 'success') return;
                setSubgroups(data.data.available_subgroups.filter(Boolean));
            })
            .catch(() => {});
    }, []);

    const hasFilters = filters.search || filters.subgroup || filters.startDate || filters.endDate;

    return (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginBottom: 16 }}>
            {/* Поиск */}
            <div style={{ position: 'relative', flex: '1 1 200px' }}>
                <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
                <input
                    style={{ ...inputStyle, paddingLeft: 30, width: '100%', boxSizing: 'border-box' }}
                    placeholder="Поиск товара"
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

            {/* Подгруппа */}
            <div style={{ position: 'relative', flex: '1 1 160px' }}>
                <select
                    style={{ ...inputStyle, cursor: 'pointer', paddingRight: 36, width: '100%', boxSizing: 'border-box', appearance: 'none', WebkitAppearance: 'none', color: filters.subgroup ? 'var(--ink)' : 'var(--muted)' }}
                    value={filters.subgroup || ''}
                    onChange={e => onChange({ ...filters, subgroup: e.target.value || '' })}
                >
                    <option value="">Все подгруппы</option>
                    {subgroups.map(sg => <option key={sg} value={sg}>{sg}</option>)}
                </select>
                <ChevronDown size={12} style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
            </div>

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
                    onClick={() => onChange({ search: '', subgroup: '', startDate: null, endDate: null })}
                    style={{ ...inputStyle, display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', color: 'var(--muted)', padding: '7px 10px' }}
                >
                    <X size={12} /> Сбросить
                </button>
            )}
        </div>
    );
};

ProductFilterPanel.propTypes = {
    filters: PropTypes.shape(FiltersPropTypes).isRequired,
    onChange: PropTypes.func.isRequired,
};

export default ProductFilterPanel;
