import { useState } from 'react';
import PropTypes from 'prop-types';
import { ChevronUp, ChevronDown, ChevronsUpDown, ChevronRight, Eye, Loader2 } from 'lucide-react';
import { suppliesApi } from '../../../api/suppliesApi';

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

const pluralSupplies = (n) => n === 1 ? '1 поставка' : n >= 2 && n <= 4 ? `${n} поставки` : `${n} поставок`;

const SupplierInfo = ({ supplier, uom }) => (
    <div style={{ padding: '10px 12px', borderRadius: 8, border: '1px solid var(--hairline)', background: 'var(--canvas)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>{supplier.name}</span>
            <span style={{ fontFamily: 'var(--sans)', fontSize: 11, background: 'var(--surface-card)', color: 'var(--muted)', borderRadius: 9999, padding: '2px 8px' }}>
                {pluralSupplies(supplier.total_supplies)}
            </span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
            <div style={{ background: 'var(--surface-soft)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Количество</div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>{fmt(supplier.total_quantity)} {uom}</div>
            </div>
            <div style={{ background: 'var(--surface-soft)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Сумма</div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>{fmt(supplier.total_sum)} ₽</div>
            </div>
            <div style={{ background: 'var(--surface-soft)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Диапазон цен</div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>
                    {supplier.price_range.min === supplier.price_range.max
                        ? `${supplier.price_range.min.toFixed(2)} ₽`
                        : `${supplier.price_range.min.toFixed(2)}–${supplier.price_range.max.toFixed(2)} ₽`}
                </div>
            </div>
            <div style={{ background: 'var(--surface-soft)', borderRadius: 6, padding: '6px 8px' }}>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Средняя цена</div>
                <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>
                    {supplier.total_quantity ? (supplier.total_sum / supplier.total_quantity).toFixed(2) : '—'} ₽/{uom}
                </div>
            </div>
        </div>
    </div>
);
SupplierInfo.propTypes = {
    supplier: PropTypes.shape({
        name: PropTypes.string.isRequired,
        total_supplies: PropTypes.number.isRequired,
        total_quantity: PropTypes.number.isRequired,
        total_sum: PropTypes.number.isRequired,
        price_range: PropTypes.shape({ min: PropTypes.number.isRequired, max: PropTypes.number.isRequired }).isRequired,
    }).isRequired,
    uom: PropTypes.string.isRequired,
};

const COLUMNS = [
    { key: 'name',           label: 'Наименование' },
    { key: 'code',           label: 'Код' },
    { key: 'group',          label: 'Группа' },
    { key: 'total_quantity', label: 'Количество' },
    { key: 'average_price',  label: 'Средняя цена' },
    { key: 'total_sum',      label: 'Сумма' },
];

const MaterialSupplyTable = ({ materials, loading, pagination, sortField, sortOrder, onSort, onPageChange, onMaterialClick, filters }) => {
    const [expandedIds, setExpandedIds] = useState([]);
    const [detailsCache, setDetailsCache] = useState({});
    const [loadingIds, setLoadingIds] = useState({});

    const cacheKey = (id) => {
        const f = filters || {};
        return `${id}:${f.startDate || ''}:${f.endDate || ''}`;
    };

    const fetchDetails = async (id) => {
        const key = cacheKey(id);
        if (detailsCache[key]) return;
        setLoadingIds(p => ({ ...p, [key]: true }));
        try {
            const params = new URLSearchParams();
            if (filters?.startDate) params.append('startDate', filters.startDate);
            if (filters?.endDate)   params.append('endDate',   filters.endDate);
            const qs = params.toString();
            const data = await suppliesApi.materials.getDetails(id, qs);
            if (data.status === 'success') setDetailsCache(p => ({ ...p, [key]: data.data }));
        } catch { /* silent */ }
        finally { setLoadingIds(p => ({ ...p, [key]: false })); }
    };

    const toggleExpand = async (row) => {
        if (expandedIds.includes(row.id)) {
            setExpandedIds(p => p.filter(id => id !== row.id));
        } else {
            await fetchDetails(row.id);
            setExpandedIds(p => [...p, row.id]);
        }
    };

    const totalPages = Math.ceil((pagination.total || 0) / pagination.pageSize) || 1;

    return (
        <div>
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <th style={{ ...thStyle(false), cursor: 'default', width: 28 }} />
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
                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan={8} style={{ ...tdStyle, textAlign: 'center', padding: '32px 0', color: 'var(--muted)' }}>
                                    <Loader2 size={16} className="animate-spin" style={{ display: 'inline-block', marginRight: 8 }} />
                                    Загрузка...
                                </td>
                            </tr>
                        ) : materials.length === 0 ? (
                            <tr>
                                <td colSpan={8} style={{ ...tdStyle, textAlign: 'center', padding: '32px 0', color: 'var(--muted)' }}>Нет данных</td>
                            </tr>
                        ) : materials.map(row => {
                            const expanded = expandedIds.includes(row.id);
                            const key = cacheKey(row.id);
                            const rowDetails = detailsCache[key];
                            const isLoadingRow = loadingIds[key];

                            return [
                                <tr key={row.id}
                                    onClick={() => toggleExpand(row)}
                                    style={{ cursor: 'pointer', transition: 'background 100ms', background: expanded ? 'var(--surface-soft)' : '' }}
                                    onMouseEnter={e => { if (!expanded) e.currentTarget.style.background = 'var(--surface-soft)'; }}
                                    onMouseLeave={e => { if (!expanded) e.currentTarget.style.background = ''; }}
                                >
                                    <td style={{ ...tdStyle, paddingRight: 4, paddingLeft: 8, width: 28 }}>
                                        <ChevronRight size={13} style={{ color: 'var(--muted)', transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }} />
                                    </td>
                                    <td style={{ ...tdStyle, fontWeight: 500, color: 'var(--ink)' }}>{row.name}</td>
                                    <td style={{ ...tdStyle, fontFamily: 'var(--mono)', fontSize: 12 }}>{row.code}</td>
                                    <td style={tdStyle}>{row.group}</td>
                                    <td style={tdStyle}>{fmt(row.total_quantity)} {row.uom}</td>
                                    <td style={tdStyle}>{(row.average_price || 0).toFixed(2)} ₽/{row.uom}</td>
                                    <td style={tdStyle}>{fmt(row.total_sum)} ₽</td>
                                    <td style={tdStyle} onClick={e => e.stopPropagation()}>
                                        <button onClick={() => onMaterialClick(row)}
                                            style={{ display: 'inline-flex', alignItems: 'center', gap: 5, background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)', fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, padding: 0 }}>
                                            <Eye size={13} /> Детали
                                        </button>
                                    </td>
                                </tr>,
                                expanded && (
                                    <tr key={`${row.id}-expanded`}>
                                        <td colSpan={8} style={{ padding: '12px 16px', background: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline-soft)' }}>
                                            {isLoadingRow ? (
                                                <div style={{ textAlign: 'center', color: 'var(--muted)', padding: '8px 0' }}>
                                                    <Loader2 size={14} className="animate-spin" style={{ display: 'inline-block' }} />
                                                </div>
                                            ) : !rowDetails?.suppliers?.length ? (
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет данных о поставщиках</span>
                                            ) : (
                                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                                                    {rowDetails.suppliers.map((s, i) => (
                                                        <SupplierInfo key={`${row.id}-${i}`} supplier={s} uom={row.uom} />
                                                    ))}
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ),
                            ];
                        })}
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

MaterialSupplyTable.propTypes = {
    materials: PropTypes.array.isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onMaterialClick: PropTypes.func.isRequired,
    filters: PropTypes.shape({ search: PropTypes.string, group: PropTypes.string, startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default MaterialSupplyTable;
