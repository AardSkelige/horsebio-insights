import { useState, useMemo } from 'react';
import PropTypes from 'prop-types';
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import { formatNumber, formatCurrency } from '../../utils/formatters';

const COLORS = {
    large:      { bg: 'rgba(204,120,92,0.1)', color: '#a0583e', border: 'rgba(204,120,92,0.3)' },
    medium:     { bg: 'rgba(92,138,204,0.1)', color: '#3a68a0', border: 'rgba(92,138,204,0.3)' },
    small:      { bg: 'rgba(92,172,106,0.1)', color: '#3a7c4a', border: 'rgba(92,172,106,0.3)' },
    rare_large: { bg: 'rgba(140,138,132,0.1)', color: '#5a5852', border: 'rgba(140,138,132,0.3)' },
};

const CATEGORY_NAMES = {
    large:      'Крупные (регулярные)',
    medium:     'Средние (регулярные)',
    small:      'Мелкие (нерегулярные)',
    rare_large: 'Крупные (редкие)',
};

const PAGE_SIZE = 10;

const SortIcon = ({ dir }) => {
    if (dir === 'asc') return <ChevronUp style={{ width: 12, height: 12 }} />;
    if (dir === 'desc') return <ChevronDown style={{ width: 12, height: 12 }} />;
    return <ChevronsUpDown style={{ width: 12, height: 12, opacity: 0.4 }} />;
};

SortIcon.propTypes = { dir: PropTypes.string };

const thStyle = (active) => ({
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: active ? 'var(--primary)' : 'var(--muted)',
    padding: '10px 12px', textAlign: 'left', borderBottom: '1px solid var(--hairline)',
    whiteSpace: 'nowrap', cursor: 'pointer', userSelect: 'none',
});

const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '11px 12px', borderBottom: '1px solid var(--hairline-soft)', verticalAlign: 'middle',
};

export const CounterpartyGroupsTable = ({ data }) => {
    const [sortKey, setSortKey] = useState('avg_monthly');
    const [sortDir, setSortDir] = useState('desc');
    const [filterCat, setFilterCat] = useState(null);
    const [page, setPage] = useState(1);

    const rows = useMemo(() => Object.entries(data.categories).flatMap(([category, cat]) =>
        cat.counterparties.map(c => ({ key: c.id, name: c.name, category, avg_monthly: c.avg_monthly, frequency: c.frequency, total_months: c.total_months, total_sum: c.total_sum }))
    ), [data]);

    const filtered = useMemo(() => filterCat ? rows.filter(r => r.category === filterCat) : rows, [rows, filterCat]);

    const sorted = useMemo(() => [...filtered].sort((a, b) => {
        const av = a[sortKey], bv = b[sortKey];
        if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        return sortDir === 'asc' ? av - bv : bv - av;
    }), [filtered, sortKey, sortDir]);

    const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const paginated = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const handleSort = (key) => {
        if (sortKey === key) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
        else { setSortKey(key); setSortDir('desc'); }
        setPage(1);
    };

    const handleFilter = (cat) => { setFilterCat(f => f === cat ? null : cat); setPage(1); };

    // eslint-disable-next-line react/prop-types
    const SortTh = ({ label, col }) => (
        <th style={thStyle(sortKey === col)} onClick={() => handleSort(col)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                {label} <SortIcon dir={sortKey === col ? sortDir : null} />
            </div>
        </th>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {/* Category filter pills */}
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                <button
                    onClick={() => handleFilter(null)}
                    style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 12px', borderRadius: '20px', cursor: 'pointer', border: '1px solid var(--hairline)', backgroundColor: !filterCat ? 'var(--ink)' : 'transparent', color: !filterCat ? 'var(--canvas)' : 'var(--muted)', transition: 'all 150ms' }}
                >
                    Все
                </button>
                {Object.entries(CATEGORY_NAMES).map(([key, name]) => {
                    const c = COLORS[key];
                    const active = filterCat === key;
                    return (
                        <button
                            key={key}
                            onClick={() => handleFilter(key)}
                            style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 12px', borderRadius: '20px', cursor: 'pointer', border: `1px solid ${active ? c.border : 'var(--hairline)'}`, backgroundColor: active ? c.bg : 'transparent', color: active ? c.color : 'var(--muted)', transition: 'all 150ms' }}
                        >
                            {name}
                        </button>
                    );
                })}
            </div>

            {/* Table */}
            <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr>
                            <SortTh label="Наименование" col="name" />
                            <th style={thStyle(false)}>Группа</th>
                            <SortTh label="Объём продаж" col="avg_monthly" />
                            <SortTh label="Активность" col="frequency" />
                            <SortTh label="Месяцев" col="total_months" />
                            <SortTh label="Общая сумма" col="total_sum" />
                        </tr>
                    </thead>
                    <tbody>
                        {paginated.map(r => {
                            const c = COLORS[r.category];
                            return (
                                <tr key={r.key}>
                                    <td style={{ ...tdStyle, fontWeight: 500, color: 'var(--ink)' }}>{r.name}</td>
                                    <td style={tdStyle}>
                                        <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: '20px', fontSize: '11px', fontWeight: 600, fontFamily: 'var(--sans)', backgroundColor: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
                                            {CATEGORY_NAMES[r.category]}
                                        </span>
                                    </td>
                                    <td style={tdStyle}>{formatCurrency(r.avg_monthly)}</td>
                                    <td style={tdStyle}>{(r.frequency * 100).toFixed(1)}%</td>
                                    <td style={tdStyle}>{formatNumber(r.total_months)}</td>
                                    <td style={tdStyle}>{formatCurrency(r.total_sum)}</td>
                                </tr>
                            );
                        })}
                        {paginated.length === 0 && (
                            <tr>
                                <td colSpan={6} style={{ ...tdStyle, textAlign: 'center', color: 'var(--muted)', padding: '32px' }}>
                                    Нет данных
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>
                    Всего {formatNumber(sorted.length)} контрагентов
                </span>
                {totalPages > 1 && (
                    <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                            onClick={() => setPage(p => Math.max(1, p - 1))}
                            disabled={page === 1}
                            style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--hairline)', backgroundColor: 'var(--canvas)', color: 'var(--body)', cursor: page === 1 ? 'not-allowed' : 'pointer', opacity: page === 1 ? 0.4 : 1 }}
                        >
                            ←
                        </button>
                        {Array.from({ length: totalPages }, (_, i) => i + 1)
                            .filter(p => p === 1 || p === totalPages || Math.abs(p - page) <= 1)
                            .reduce((acc, p, i, arr) => {
                                if (i > 0 && arr[i - 1] !== p - 1) acc.push('…');
                                acc.push(p);
                                return acc;
                            }, [])
                            .map((p, i) => p === '…' ? (
                                <span key={`ellipsis-${i}`} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 6px', color: 'var(--muted)' }}>…</span>
                            ) : (
                                <button key={p} onClick={() => setPage(p)} style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: `1px solid ${p === page ? 'var(--primary)' : 'var(--hairline)'}`, backgroundColor: p === page ? 'var(--primary)' : 'var(--canvas)', color: p === page ? '#fff' : 'var(--body)', cursor: 'pointer' }}>
                                    {p}
                                </button>
                            ))
                        }
                        <button
                            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                            disabled={page === totalPages}
                            style={{ fontFamily: 'var(--sans)', fontSize: '12px', padding: '4px 10px', borderRadius: '6px', border: '1px solid var(--hairline)', backgroundColor: 'var(--canvas)', color: 'var(--body)', cursor: page === totalPages ? 'not-allowed' : 'pointer', opacity: page === totalPages ? 0.4 : 1 }}
                        >
                            →
                        </button>
                    </div>
                )}
            </div>

            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.7 }}>
                Объём продаж — среднемесячный показатель за период · Активность — % месяцев с заказами · Нажмите заголовок для сортировки
            </div>
        </div>
    );
};

CounterpartyGroupsTable.propTypes = {
    data: PropTypes.shape({
        categories: PropTypes.objectOf(PropTypes.shape({
            counterparties: PropTypes.arrayOf(PropTypes.shape({
                id: PropTypes.number.isRequired,
                name: PropTypes.string.isRequired,
                avg_monthly: PropTypes.number.isRequired,
                frequency: PropTypes.number.isRequired,
                total_months: PropTypes.number.isRequired,
                total_sum: PropTypes.number.isRequired,
            })).isRequired,
        })).isRequired,
    }).isRequired,
};

export default CounterpartyGroupsTable;
