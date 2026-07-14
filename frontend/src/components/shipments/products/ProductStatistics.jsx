import PropTypes from 'prop-types';
import { StatisticsPropTypes } from './types';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');
const fmtRub = (v) => (v ?? 0).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0, maximumFractionDigits: 0 });

const TopList = ({ title, items, renderItem, maxValue }) => (
    <div style={{ background: 'var(--surface-card)', borderRadius: 12, padding: '16px 20px', border: '1px solid var(--hairline)' }}>
        <div style={{ fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 14 }}>
            {title}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {items.map((item, i) => {
                const pct = maxValue ? (item._val / maxValue) * 100 : 0;
                return (
                    <div key={i}>
                        <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', marginBottom: 4, lineHeight: 1.3 }}>{item.name}</div>
                        {renderItem(item)}
                        <div style={{ height: 2, borderRadius: 9999, background: 'var(--hairline)', marginTop: 6, overflow: 'hidden' }}>
                            <div style={{ height: '100%', width: `${pct}%`, background: 'var(--primary)', borderRadius: 9999 }} />
                        </div>
                    </div>
                );
            })}
        </div>
    </div>
);
TopList.propTypes = {
    title: PropTypes.string.isRequired,
    items: PropTypes.array.isRequired,
    renderItem: PropTypes.func.isRequired,
    maxValue: PropTypes.number,
};

const ProductStatistics = ({ stats }) => {
    const byQty = (stats.top_by_quantity || []).map(i => ({ ...i, _val: i.quantity }));
    const byRev = (stats.top_by_revenue || []).map(i => ({ ...i, _val: i.revenue }));
    const byAvg = (stats.top_by_average_quantity || []).map(i => ({ ...i, _val: parseFloat(i.average_quantity) || 0 }));

    return (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12, marginBottom: 20 }}>
            <TopList
                title="Топ по количеству"
                items={byQty}
                maxValue={byQty[0]?._val}
                renderItem={(item) => (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontFamily: 'var(--serif)', fontSize: 16, fontWeight: 400, color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{fmt(item.quantity)} шт.</span>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--muted)', alignSelf: 'flex-end' }}>{item.shipments_count} отгрузок</span>
                    </div>
                )}
            />
            <TopList
                title="Топ по выручке"
                items={byRev}
                maxValue={byRev[0]?._val}
                renderItem={(item) => (
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontFamily: 'var(--serif)', fontSize: 16, fontWeight: 400, color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{fmtRub(item.revenue)}</span>
                        <span style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--muted)', alignSelf: 'flex-end' }}>{fmt(item.price_per_unit)} ₽/шт.</span>
                    </div>
                )}
            />
            <TopList
                title="Топ по среднему"
                items={byAvg}
                maxValue={byAvg[0]?._val}
                renderItem={(item) => (
                    <span style={{ fontFamily: 'var(--serif)', fontSize: 16, fontWeight: 400, color: 'var(--ink)', fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>{item.average_quantity} шт.</span>
                )}
            />
        </div>
    );
};

ProductStatistics.propTypes = {
    stats: PropTypes.shape(StatisticsPropTypes).isRequired,
};

export default ProductStatistics;
