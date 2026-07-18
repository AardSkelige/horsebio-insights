import PropTypes from 'prop-types';
import { ChevronUp, ChevronDown, ChevronsUpDown, Eye } from 'lucide-react';
import { SupplierPropTypes } from './types';
import { SkeletonRows } from '../../ui/Skeleton';
import { useRowHoverPill } from '../../ui/motion';

const thStyle = (active) => ({
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500,
    letterSpacing: '0.07em', textTransform: 'uppercase',
    color: active ? 'var(--primary)' : 'var(--muted)',
    padding: '9px 12px', textAlign: 'left',
    borderBottom: '1px solid var(--hairline)',
    whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none',
    background: 'var(--canvas)',
});

const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--body)',
    padding: '10px 12px', borderBottom: '1px solid var(--hairline-soft)',
    verticalAlign: 'middle',
};

const SortIcon = ({ active, order }) => {
    if (!active) return <ChevronsUpDown size={11} style={{ opacity: 0.4, marginLeft: 3 }} />;
    return order === 'asc'
        ? <ChevronUp size={11} style={{ color: 'var(--primary)', marginLeft: 3 }} />
        : <ChevronDown size={11} style={{ color: 'var(--primary)', marginLeft: 3 }} />;
};
SortIcon.propTypes = { active: PropTypes.bool, order: PropTypes.string };

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');
const fmtDate = (d) => d ? new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';

const COLUMNS = [
    { key: 'name',           label: 'Наименование' },
    { key: 'supplies_count', label: 'Приёмок' },
    { key: 'positions_count', label: 'Позиции' },
    { key: 'unique_materials', label: 'Материалов' },
    { key: 'total_sum',      label: 'Общая сумма' },
    { key: 'avg_supply_sum', label: 'Средняя сумма' },
    { key: 'last_supply',    label: 'Последняя приёмка' },
];

const SupplierTable = ({ suppliers, loading, pagination, sortField, sortOrder, onSort, onPageChange, onSupplierClick }) => {
    const totalPages = Math.ceil((pagination.total || 0) / pagination.pageSize) || 1;
    const { containerProps, rowHoverProps, pill } = useRowHoverPill();

    return (
        <div>
            <div {...containerProps} style={{ ...containerProps.style, overflowX: 'auto' }}>
                {pill}
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            {COLUMNS.map(col => (
                                <th key={col.key} style={thStyle(sortField === col.key)} onClick={() => onSort(col.key)}>
                                    <div style={{ display: 'flex', alignItems: 'center' }}>
                                        {col.label}
                                        <SortIcon active={sortField === col.key} order={sortOrder} />
                                    </div>
                                </th>
                            ))}
                            <th style={{ ...thStyle(false), cursor: 'default' }}>Детали</th>
                        </tr>
                    </thead>
                    <tbody style={{ opacity: loading && suppliers.length > 0 ? 0.45 : 1, transition: 'opacity 200ms ease' }}>
                        {loading && suppliers.length === 0 ? (
                            <SkeletonRows cols={8} />
                        ) : !loading && suppliers.length === 0 ? (
                            <tr>
                                <td colSpan={8} style={{ ...tdStyle, textAlign: 'center', padding: '32px 0', color: 'var(--muted)' }}>Нет данных</td>
                            </tr>
                        ) : suppliers.map(row => (
                            <tr key={row.id} {...rowHoverProps}>
                                <td style={{ ...tdStyle, fontWeight: 500, color: 'var(--ink)' }}>{row.name}</td>
                                <td style={tdStyle}>{fmt(row.supplies_count)}</td>
                                <td style={tdStyle}>{fmt(row.positions_count)}</td>
                                <td style={tdStyle}>{fmt(row.unique_materials)}</td>
                                <td style={tdStyle}>{fmt(row.total_sum)} ₽</td>
                                <td style={tdStyle}>{fmt(row.avg_supply_sum)} ₽</td>
                                <td style={tdStyle}>{fmtDate(row.last_supply)}</td>
                                <td style={tdStyle}>
                                    <button onClick={() => onSupplierClick(row)}
                                        style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)', fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, padding: 0 }}>
                                        <Eye size={13} /> Детали
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* Пагинация */}
            {pagination.total > pagination.pageSize && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 4px 4px', marginTop: 4 }}>
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>
                        {pagination.total} записей · стр. {pagination.current} из {totalPages}
                    </span>
                    <div style={{ display: 'flex', gap: 4 }}>
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                            .filter(p => p === 1 || p === totalPages || Math.abs(p - pagination.current) <= 2)
                            .reduce((acc, p, i, arr) => { if (i > 0 && p - arr[i - 1] > 1) acc.push('…'); acc.push(p); return acc; }, [])
                            .map((p, i) => p === '…' ? (
                                <span key={`e-${i}`} style={{ padding: '4px 6px', fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>…</span>
                            ) : (
                                <button key={p} onClick={() => onPageChange(p)}
                                    style={{ minWidth: 28, padding: '4px 6px', borderRadius: 6, border: p === pagination.current ? '1px solid var(--primary)' : '1px solid var(--hairline)', background: p === pagination.current ? 'var(--primary)' : 'var(--canvas)', color: p === pagination.current ? '#fff' : 'var(--body)', fontFamily: 'var(--sans)', fontSize: 12, cursor: 'pointer' }}>
                                    {p}
                                </button>
                            ))
                        }
                    </div>
                </div>
            )}
        </div>
    );
};

SupplierTable.propTypes = {
    suppliers: PropTypes.arrayOf(PropTypes.shape(SupplierPropTypes)).isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onSupplierClick: PropTypes.func.isRequired,
};

export default SupplierTable;
