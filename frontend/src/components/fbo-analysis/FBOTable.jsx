import PropTypes from 'prop-types';
import { useState } from 'react';
import { ArrowUp, ArrowDown } from 'lucide-react';

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Math.round(n));

const thBase = {
    padding: '8px 12px',
    fontFamily: 'var(--sans)',
    fontSize: '11px',
    fontWeight: 500,
    letterSpacing: '0.07em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    textAlign: 'left',
    cursor: 'pointer',
    userSelect: 'none',
    whiteSpace: 'nowrap',
    borderBottom: '1px solid var(--hairline)',
    backgroundColor: 'var(--canvas)',
};

const SortHeader = ({ label, sortKey, sortConfig, onSort, align = 'left' }) => {
    const active = sortConfig.key === sortKey;
    return (
        <th onClick={() => onSort(sortKey)} style={{ ...thBase, textAlign: align }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                {label}
                <span style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
                    <ArrowUp style={{ width: 9, height: 9, color: active && sortConfig.direction === 'asc' ? 'var(--primary)' : 'var(--hairline)' }} />
                    <ArrowDown style={{ width: 9, height: 9, color: active && sortConfig.direction === 'desc' ? 'var(--primary)' : 'var(--hairline)' }} />
                </span>
            </span>
        </th>
    );
};

SortHeader.propTypes = {
    label: PropTypes.string.isRequired,
    sortKey: PropTypes.string.isRequired,
    align: PropTypes.string,
    sortConfig: PropTypes.shape({ key: PropTypes.string.isRequired, direction: PropTypes.string.isRequired }).isRequired,
    onSort: PropTypes.func.isRequired,
};

const FBOTable = ({ products }) => {
    const [sortConfig, setSortConfig] = useState({ key: 'fbo_quantity', direction: 'desc' });

    const sorted = [...products].sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) return sortConfig.direction === 'asc' ? -1 : 1;
        if (a[sortConfig.key] > b[sortConfig.key]) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
    });

    const handleSort = (key) => setSortConfig(prev => ({
        key,
        direction: prev.key === key && prev.direction === 'asc' ? 'desc' : 'asc',
    }));

    if (products.length === 0) return (
        <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', textAlign: 'center', padding: '32px 0' }}>
            Нет данных для отображения
        </p>
    );

    return (
        <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                    <tr>
                        <SortHeader label="Наименование" sortKey="name" sortConfig={sortConfig} onSort={handleSort} />
                        <SortHeader label="FBO заказ"    sortKey="fbo_quantity"      align="right" sortConfig={sortConfig} onSort={handleSort} />
                        <SortHeader label="Остаток"      sortKey="stock"             align="right" sortConfig={sortConfig} onSort={handleSort} />
                        <SortHeader label="Продажи"      sortKey="sales_30_days"     align="right" sortConfig={sortConfig} onSort={handleSort} />
                        <SortHeader label="Нужно произвести" sortKey="production_needed" align="right" sortConfig={sortConfig} onSort={handleSort} />
                    </tr>
                </thead>
                <tbody>
                    {sorted.map((p) => (
                        <tr key={p.name} style={{ borderBottom: '1px solid var(--hairline)' }}
                            onMouseEnter={e => (e.currentTarget.style.backgroundColor = 'var(--surface-card)')}
                            onMouseLeave={e => (e.currentTarget.style.backgroundColor = 'transparent')}
                        >
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>
                                {p.name}
                            </td>
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>
                                {fmt(p.fbo_quantity)}
                            </td>
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>
                                {fmt(p.stock)}
                            </td>
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>
                                {fmt(p.sales_30_days)}
                            </td>
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', fontWeight: 500, textAlign: 'right', color: p.production_needed > 0 ? '#dc2626' : '#059669' }}>
                                {fmt(p.production_needed)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

FBOTable.propTypes = {
    products: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string.isRequired,
        fbo_quantity: PropTypes.number.isRequired,
        stock: PropTypes.number.isRequired,
        sales_30_days: PropTypes.number.isRequired,
        production_needed: PropTypes.number.isRequired,
    })).isRequired,
};

export default FBOTable;
