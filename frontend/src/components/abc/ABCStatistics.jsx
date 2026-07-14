import PropTypes from 'prop-types';

const COLORS = {
    A: { color: '#a0583e', bg: 'rgba(204,120,92,0.1)',  border: 'rgba(204,120,92,0.3)',  bar: '#cc785c' },
    B: { color: '#3a68a0', bg: 'rgba(92,138,204,0.1)',  border: 'rgba(92,138,204,0.3)',  bar: '#5c8acc' },
    C: { color: '#7a6010', bg: 'rgba(204,156,58,0.1)',  border: 'rgba(204,156,58,0.3)',  bar: '#cc9c3a' },
};

const fmtCurrency = (v) => new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(v);

const thStyle = {
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 600,
    letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--muted)',
    padding: '10px 14px', textAlign: 'left', borderBottom: '1px solid var(--hairline)',
};
const tdStyle = {
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)',
    padding: '14px', borderBottom: '1px solid var(--hairline-soft)', verticalAlign: 'middle',
};

export const ABCStatistics = ({ data }) => {
    if (!data?.categories) return null;

    const rows = Object.entries(data.categories).map(([category, cat]) => {
        const m = cat.metrics;
        const productsShare = ((m.product_count / data.total_statistics.total_products) * 100).toFixed(1);
        return { category, products: m.product_count, productsShare, revenue: m.revenue, revenueShare: m.revenue_share };
    });

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', minWidth: 340, borderCollapse: 'collapse' }}>
                <thead>
                    <tr>
                        <th style={thStyle}>Категория</th>
                        <th style={thStyle}>Продукты</th>
                        <th style={{ ...thStyle, minWidth: '200px' }}>Выручка</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map(r => {
                        const c = COLORS[r.category] || COLORS.C;
                        return (
                            <tr key={r.category}>
                                <td style={tdStyle}>
                                    <span style={{ display: 'inline-block', padding: '3px 10px', borderRadius: '20px', fontSize: '13px', fontWeight: 700, backgroundColor: c.bg, color: c.color, border: `1px solid ${c.border}` }}>
                                        {r.category}
                                    </span>
                                </td>
                                <td style={tdStyle}>
                                    <div style={{ fontWeight: 500 }}>{r.products} SKU</div>
                                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{r.productsShare}% от общего</div>
                                </td>
                                <td style={tdStyle}>
                                    <div style={{ fontWeight: 500, marginBottom: 6 }}>{fmtCurrency(r.revenue)}</div>
                                    <div style={{ height: 4, borderRadius: 2, backgroundColor: 'var(--surface-cream-strong)', overflow: 'hidden', marginBottom: 4 }}>
                                        <div style={{ height: '100%', borderRadius: 2, backgroundColor: c.bar, width: `${(r.revenueShare * 100).toFixed(1)}%`, transition: 'width 400ms ease' }} />
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{(r.revenueShare * 100).toFixed(1)}% от общей выручки</div>
                                </td>
                            </tr>
                        );
                    })}
                </tbody>
            </table>
            </div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', backgroundColor: 'var(--surface-soft)', padding: '10px 14px', borderRadius: '8px', lineHeight: 1.7 }}>
                SKU — уникальные товарные позиции · Прогресс-бар — вклад категории в общую выручку
            </div>
        </div>
    );
};

ABCStatistics.propTypes = {
    data: PropTypes.shape({
        categories: PropTypes.object.isRequired,
        total_statistics: PropTypes.shape({ total_products: PropTypes.number.isRequired }).isRequired,
    }).isRequired,
};

export default ABCStatistics;
