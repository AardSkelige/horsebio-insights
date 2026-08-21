import PropTypes from 'prop-types';
import { Badge, DataTable } from '../ui';
import { money } from '../../utils/formatters';

const COLORS = {
    A: { color: 'var(--primary-active)', bg: 'var(--accent-bg)',  border: 'var(--accent-border)',  bar: 'var(--primary)' },
    B: { color: 'var(--info-ink)', bg: 'var(--info-bg)',  border: 'var(--info-border)',  bar: 'var(--info)' },
    C: { color: 'var(--warning-ink)', bg: 'var(--warning-bg)',  border: 'var(--warning-border)',  bar: 'var(--warning)' },
};



export // Категория A — лучшая, C — хвост; тон бейджа берётся из общей семантики
const CATEGORY_TONE = { A: 'accent', B: 'info', C: 'warning' };

export const ABCStatistics = ({ data }) => {
    if (!data?.categories) return null;

    const rows = Object.entries(data.categories).map(([category, cat]) => {
        const m = cat.metrics;
        const productsShare = ((m.product_count / data.total_statistics.total_products) * 100).toFixed(1);
        return { category, products: m.product_count, productsShare, revenue: m.revenue, revenueShare: m.revenue_share };
    });

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <DataTable
                columns={[
                    {
                        key: 'category',
                        label: 'Категория',
                        sortable: false,
                        render: (r) => <Badge tone={CATEGORY_TONE[r.category] || 'neutral'}>{r.category}</Badge>,
                    },
                    {
                        key: 'products',
                        label: 'Продукты',
                        sortable: false,
                        render: (r) => (
                            <>
                                <div style={{ fontWeight: 500 }}>{r.products} SKU</div>
                                <div style={{ fontSize: 'var(--size-xs)', color: 'var(--muted)' }}>{r.productsShare}% от общего</div>
                            </>
                        ),
                    },
                    {
                        key: 'revenue',
                        label: 'Выручка',
                        sortable: false,
                        render: (r) => (
                            <div style={{ minWidth: 200 }}>
                                <div style={{ fontWeight: 500, marginBottom: 6 }}>{money(r.revenue)}</div>
                                <div style={{ height: 4, borderRadius: 2, backgroundColor: 'var(--surface-cream-strong)', overflow: 'hidden', marginBottom: 4 }}>
                                    <div style={{
                                        height: '100%', borderRadius: 2,
                                        backgroundColor: (COLORS[r.category] || COLORS.C).bar,
                                        width: `${(r.revenueShare * 100).toFixed(1)}%`,
                                        transition: 'width 400ms ease',
                                    }} />
                                </div>
                                <div style={{ fontSize: 'var(--size-xs)', color: 'var(--muted)' }}>
                                    {(r.revenueShare * 100).toFixed(1)}% от общей выручки
                                </div>
                            </div>
                        ),
                    },
                ]}
                rows={rows}
                rowKey="category"
            />
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
