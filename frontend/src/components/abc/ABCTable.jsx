import { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { formatNumber, formatCurrency } from '../../utils/formatters';

const COLORS = {
    A: { color: '#a0583e', bg: 'rgba(204,120,92,0.1)',  border: 'rgba(204,120,92,0.3)'  },
    B: { color: '#3a68a0', bg: 'rgba(92,138,204,0.1)',  border: 'rgba(92,138,204,0.3)'  },
    C: { color: '#7a6010', bg: 'rgba(204,156,58,0.1)',  border: 'rgba(204,156,58,0.3)'  },
};

const PAGE_SIZE = 10;

const SortIcon = ({ dir }) => {
    if (dir === 'asc')  return <ChevronUp   style={{ width: 12, height: 12 }} />;
    if (dir === 'desc') return <ChevronDown style={{ width: 12, height: 12 }} />;
    return <ChevronsUpDown style={{ width: 12, height: 12, opacity: 0.4 }} />;
};

const thBase = (active) => ({
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase',
    color: active ? 'var(--primary)' : 'var(--muted)',
    padding: '10px 12px', textAlign: 'left',
    borderBottom: '1px solid var(--hairline)',
    whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none',
});

const tdBase = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '11px 12px', borderBottom: '1px solid var(--hairline-soft)',
    verticalAlign: 'middle',
};

export const ABCTable = ({ data }) => {
    const [sortKey, setSortKey] = useState('revenue');
    const [sortDir, setSortDir] = useState('desc');
    const [filterCat, setFilterCat] = useState(null);
    const [page, setPage] = useState(1);

    const filtered = useMemo(() =>
        filterCat ? data.filter(r => r.metrics.category === filterCat) : data,
        [data, filterCat]
    );

    const sorted = useMemo(() => [...filtered].sort((a, b) => {
        const getVal = (r) => {
            if (sortKey === 'name')         return r.product.name;
            if (sortKey === 'category')     return r.metrics.category;
            if (sortKey === 'revenue')      return r.metrics.revenue;
            if (sortKey === 'revenue_share')return r.metrics.revenue_share;
            if (sortKey === 'quantity')     return r.metrics.quantity;
            if (sortKey === 'orders_count') return r.metrics.orders_count;
            return '';
        };
        const av = getVal(a), bv = getVal(b);
        if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        return sortDir === 'asc' ? av - bv : bv - av;
    }), [filtered, sortKey, sortDir]);

    const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const paginated  = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const handleSort = (key) => {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('desc'); }
        setPage(1);
    };

    const handleFilter = (cat) => { setFilterCat(f => f === cat ? null : cat); setPage(1); };

    // eslint-disable-next-line react/prop-types
    const SortTh = ({ label, col }) => (
        <th style={thBase(sortKey === col)} onClick={() => handleSort(col)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                {label} <SortIcon dir={sortKey === col ? sortDir : null} />
            </div>
        </th>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Filter pills */}
            <div style={{ display: 'flex', gap: '6px' }}>
                <button onClick={() => handleFilter(null)} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 12px', borderRadius: '20px', cursor: 'pointer', border: '1px solid var(--hairline)', backgroundColor: !filterCat ? 'var(--ink)' : 'transparent', color: !filterCat ? 'var(--canvas)' : 'var(--muted)', transition: 'all 150ms' }}>
                    Все
                </button>
                {['A', 'B', 'C'].map(cat => {
                    const c = COLORS[cat];
                    const active = filterCat === cat;
                    return (
                        <button key={cat} onClick={() => handleFilter(cat)} style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 600, padding: '4px 14px', borderRadius: '20px', cursor: 'pointer', border: `1px solid ${active ? c.border : 'var(--hairline)'}`, backgroundColor: active ? c.bg : 'transparent', color: active ? c.color : 'var(--muted)', transition: 'all 150ms' }}>
                            {cat}
                        </button>
                    );
                })}
            </div>

            {/* Table */}
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <SortTh label="Наименование"   col="name" />
                            <SortTh label="Категория"      col="category" />
                            <SortTh label="Выручка"        col="revenue" />
                            <SortTh label="Доля"           col="revenue_share" />
                            <SortTh label="Количество"     col="quantity" />
                            <SortTh label="Заказов"        col="orders_count" />
                        </tr>
                    </thead>
                    <tbody>
                        {paginated.map(r => {
                            const c = COLORS[r.metrics.category] || COLORS.C;
                            return (
                                <tr key={r.product.id}>
                                    <td style={{ ...tdBase, fontWeight: 500, color: 'var(--ink)' }}>
                                        {r.product.name}
                                        {r.product.article && <div style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 400 }}>{r.product.article}</div>}
                                    </td>
                                    <td style={tdBase}>
                                        <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: '20px', fontSize: '12px', fontWeight: 700, backgroundColor: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
                                            {r.metrics.category}
                                        </span>
                                    </td>
                                    <td style={tdBase}>{formatCurrency(r.metrics.revenue)}</td>
                                    <td style={tdBase}>{(r.metrics.revenue_share * 100).toFixed(2)}%</td>
                                    <td style={tdBase}>{formatNumber(r.metrics.quantity)}</td>
                                    <td style={tdBase}>{formatNumber(r.metrics.orders_count)}</td>
                                </tr>
                            );
                        })}
                        {paginated.length === 0 && (
                            <tr><td colSpan={6} style={{ ...tdBase, textAlign: 'center', color: 'var(--muted)', padding: '32px' }}>Нет данных</td></tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>
                    Всего {sorted.length} записей
                </span>
                {totalPages > 1 && (
                    <div style={{ display: 'flex', gap: '4px' }}>
                        <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--hairline)', backgroundColor: 'var(--canvas)', color: 'var(--body)', cursor: page === 1 ? 'not-allowed' : 'pointer', opacity: page === 1 ? 0.4 : 1 }}>←</button>
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                            .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                            .reduce((acc, p, i, arr) => { if (i > 0 && arr[i - 1] !== p - 1) acc.push('…'); acc.push(p); return acc; }, [])
                            .map((p, i) => p === '…'
                                ? <span key={`e${i}`} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 6px', color: 'var(--muted)' }}>…</span>
                                : <button key={p} onClick={() => setPage(p)} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: `1px solid ${p === page ? 'var(--primary)' : 'var(--hairline)'}`, backgroundColor: p === page ? 'var(--primary)' : 'var(--canvas)', color: p === page ? '#fff' : 'var(--body)', cursor: 'pointer' }}>{p}</button>
                            )
                        }
                        <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--hairline)', backgroundColor: 'var(--canvas)', color: 'var(--body)', cursor: page === totalPages ? 'not-allowed' : 'pointer', opacity: page === totalPages ? 0.4 : 1 }}>→</button>
                    </div>
                )}
            </div>
        </div>
    );
};

SortIcon.propTypes = { dir: PropTypes.string };

ABCTable.propTypes = {
    data: PropTypes.arrayOf(PropTypes.shape({
        product: PropTypes.shape({ id: PropTypes.number.isRequired, name: PropTypes.string.isRequired, article: PropTypes.string }).isRequired,
        metrics: PropTypes.shape({ category: PropTypes.string.isRequired, revenue: PropTypes.number.isRequired, revenue_share: PropTypes.number.isRequired, quantity: PropTypes.number.isRequired, orders_count: PropTypes.number.isRequired }).isRequired,
    })).isRequired,
};

export default ABCTable;
