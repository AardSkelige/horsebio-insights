import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { X, ChevronRight, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { formatDate } from '../../../utils/formatters';
import { CHART_ANIMATION } from '../../../utils/chartAnimation';
import SectionLabel from '../../ui/SectionLabel';
import StatCard from '../../ui/StatCard';
import { ModalShell } from '../../ui/motion';
import { materialsApi } from '../../../api/materialsApi';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

const ProductCard = ({ product, totalUsage, uom }) => {
    const pct = totalUsage ? (product.quantity / totalUsage) * 100 : 0;
    return (
        <div style={{ background: 'var(--surface-card)', borderRadius: 10, padding: '12px 14px', border: '1px solid var(--hairline)' }}>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)', marginBottom: 8, lineHeight: 1.35 }}>{product.name}</div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>{fmt(product.quantity)} {uom}</span>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--primary)', fontWeight: 500 }}>{pct.toFixed(1)}%</span>
            </div>
            <div style={{ height: 3, borderRadius: 9999, background: 'var(--hairline)', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${pct}%`, background: 'var(--primary)', borderRadius: 9999 }} />
            </div>
        </div>
    );
};
ProductCard.propTypes = {
    product: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string, quantity: PropTypes.number }).isRequired,
    totalUsage: PropTypes.number,
    uom: PropTypes.string.isRequired,
};

const HistoryGroup = ({ date, group, uom }) => {
    const [open, setOpen] = useState(false);
    return (
        <div style={{ borderBottom: '1px solid var(--hairline-soft)' }}>
            <button
                onClick={() => setOpen(o => !o)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ChevronRight size={13} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)' }}>{formatDate(date)}</span>
                </div>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>
                    {group.items.length} отгрузок · {fmt(group.totalQuantity)} {uom}
                </span>
            </button>
            {open && (
                <div style={{ paddingBottom: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {group.items.map((item, i) => (
                        <div key={`${item.shipment_number}-${i}`} style={{ background: 'var(--surface-soft)', borderRadius: 8, padding: '8px 12px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                            <div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, color: 'var(--ink)' }}>№{item.shipment_number}</div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>{item.product_name}</div>
                            </div>
                            <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', whiteSpace: 'nowrap' }}>{fmt(item.quantity)} {uom}</span>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
HistoryGroup.propTypes = {
    date: PropTypes.string.isRequired,
    group: PropTypes.shape({ items: PropTypes.array, totalQuantity: PropTypes.number }).isRequired,
    uom: PropTypes.string.isRequired,
};

const MaterialDetailsModal = ({ material, visible, onClose, dateRange }) => {
    const [details, setDetails] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!material?.id || !visible) return;
        const ctrl = new AbortController();
        setLoading(true);
        setDetails(null);

        const params = new URLSearchParams();
        if (dateRange?.startDate) params.append('startDate', dateRange.startDate);
        if (dateRange?.endDate)   params.append('endDate',   dateRange.endDate);
        const qs = params.toString();

        materialsApi.getDetails(material.id, qs, ctrl.signal)
            .then(data => { if (data.status === 'success' && data.data) setDetails(data.data); })
            .catch(() => {})
            .finally(() => setLoading(false));

        return () => ctrl.abort();
    }, [material, visible, dateRange]);

    useEffect(() => {
        if (!visible) return;
        const handler = (e) => { if (e.key === 'Escape') onClose(); };
        document.addEventListener('keydown', handler);
        return () => document.removeEventListener('keydown', handler);
    }, [visible, onClose]);

    const chartData = details?.monthly_usage?.map(item => ({
        month: new Date(item.month).toLocaleDateString('ru', { month: 'short', year: '2-digit' }),
        quantity: item.quantity,
    })) || [];

    const groupedHistory = details?.usage_history?.reduce((acc, item) => {
        const date = item.date.split('T')[0];
        if (!acc[date]) acc[date] = { items: [], totalQuantity: 0 };
        acc[date].items.push(item);
        acc[date].totalQuantity += item.quantity;
        return acc;
    }, {}) || {};

    return (
        <ModalShell open={visible} onClose={onClose} maxWidth={960}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
                        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0, lineHeight: 1.2 }}>{material?.name}</h2>
                        {material?.code && <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)' }}>{material.code}</span>}
                    </div>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4, flexShrink: 0 }}>
                        <X size={18} />
                    </button>
                </div>

                {/* Body */}
                <div style={{ overflowY: 'auto', padding: '20px 24px 24px', flex: 1 }}>
                    {loading ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 240, color: 'var(--muted)' }}>
                            <Loader2 size={20} className="animate-spin" />
                        </div>
                    ) : !details ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)' }}>
                            Нет данных
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
                            {/* Stats */}
                            <div>
                                <SectionLabel>Статистика</SectionLabel>
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                                    <StatCard title="Всего использовано" value={`${fmt(details.statistics.total_usage)} ${details.material.uom}`} />
                                    <StatCard title="Отгрузок" value={fmt(details.statistics.total_shipments)} />
                                    <StatCard title="Продуктов" value={fmt(details.statistics.total_products)} />
                                </div>
                            </div>

                            {/* Chart */}
                            {chartData.length > 0 && (
                                <div>
                                    <SectionLabel>Динамика по месяцам</SectionLabel>
                                    <div style={{ height: 240 }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                                <XAxis dataKey="month" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} interval="preserveStartEnd" />
                                                <YAxis tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} tickFormatter={fmt} width={56} />
                                                <Tooltip
                                                    contentStyle={{ fontFamily: 'var(--sans)', fontSize: 12, borderRadius: 8, border: '1px solid var(--hairline)', background: 'var(--canvas)' }}
                                                    formatter={(v) => [`${fmt(v)} ${details.material.uom}`, 'Количество']}
                                                />
                                                <Line {...CHART_ANIMATION} type="monotone" dataKey="quantity" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: 'var(--primary)' }} activeDot={{ r: 5 }} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Two-column: products + history */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 20 }}>
                                {/* Product usage */}
                                <div>
                                    <SectionLabel>Использование в продуктах</SectionLabel>
                                    <div style={{ maxHeight: 400, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        {details.product_usage?.map(p => (
                                            <ProductCard
                                                key={p.id}
                                                product={p}
                                                totalUsage={details.statistics.total_usage}
                                                uom={details.material.uom}
                                            />
                                        ))}
                                    </div>
                                </div>

                                {/* Usage history */}
                                <div>
                                    <SectionLabel>История использования</SectionLabel>
                                    <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                                        {Object.entries(groupedHistory).map(([date, group]) => (
                                            <HistoryGroup key={date} date={date} group={group} uom={details.material.uom} />
                                        ))}
                                        {Object.keys(groupedHistory).length === 0 && (
                                            <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет истории</span>
                                        )}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
        </ModalShell>
    );
};

MaterialDetailsModal.propTypes = {
    material: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string, code: PropTypes.string }),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    dateRange: PropTypes.shape({ startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default MaterialDetailsModal;
