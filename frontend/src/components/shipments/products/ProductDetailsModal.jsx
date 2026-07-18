import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { X, ChevronRight, Loader2 } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { formatDateTime } from '../../../utils/formatters';
import { CHART_ANIMATION } from '../../../utils/chartAnimation';
import SectionLabel from '../../ui/SectionLabel';
import StatCard from '../../ui/StatCard';
import { ModalShell } from '../../ui/motion';
import { productsApi } from '../../../api/productsApi';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');
const fmtRub = (v) => (v ?? 0).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 0, maximumFractionDigits: 0 });
const fmtRub2 = (v) => (v ?? 0).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB', minimumFractionDigits: 2, maximumFractionDigits: 2 });

const ChartTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null;
    return (
        <div style={{ background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, padding: '8px 12px', fontFamily: 'var(--sans)', fontSize: 12 }}>
            <div style={{ color: 'var(--muted)', marginBottom: 4 }}>{label}</div>
            {payload.map((entry, i) => (
                <div key={i} style={{ color: entry.color }}>
                    {entry.name}: {entry.name === 'Количество' ? `${fmt(entry.value)} шт.` : fmtRub(entry.value)}
                </div>
            ))}
        </div>
    );
};
ChartTooltip.propTypes = { active: PropTypes.bool, payload: PropTypes.array, label: PropTypes.string };

const ShipmentRow = ({ shipment }) => {
    const [open, setOpen] = useState(false);
    return (
        <div style={{ borderBottom: '1px solid var(--hairline-soft)' }}>
            <button onClick={() => setOpen(o => !o)}
                style={{ width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 0', background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <ChevronRight size={13} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)' }}>{formatDateTime(shipment.date)}</span>
                </div>
                <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--primary)', fontWeight: 500 }}>{fmtRub(shipment.total)}</span>
            </button>
            {open && (
                <div style={{ paddingBottom: 10 }}>
                    <div style={{ background: 'var(--surface-soft)', borderRadius: 8, padding: '10px 14px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Номер</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>№{shipment.number}</div>
                        </div>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Количество</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{fmt(shipment.quantity)} шт.</div>
                        </div>
                        <div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 10, color: 'var(--muted)', marginBottom: 2 }}>Цена/шт.</div>
                            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>{fmtRub2(shipment.price)}</div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
ShipmentRow.propTypes = {
    shipment: PropTypes.shape({ number: PropTypes.string, date: PropTypes.string, quantity: PropTypes.number, price: PropTypes.number, total: PropTypes.number }).isRequired,
};

const ProductDetailsModal = ({ product, visible, onClose, dateRange }) => {
    const [details, setDetails] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!product?.id || !visible) return;
        const ctrl = new AbortController();
        setLoading(true);
        setDetails(null);

        const params = new URLSearchParams();
        if (dateRange?.startDate) params.append('startDate', dateRange.startDate);
        if (dateRange?.endDate)   params.append('endDate',   dateRange.endDate);
        const qs = params.toString();

        productsApi.getDetails(product.id, qs, ctrl.signal)
            .then(data => { if (data.status === 'success') setDetails(data.data); })
            .catch(() => {})
            .finally(() => setLoading(false));

        return () => ctrl.abort();
    }, [product, visible, dateRange]);

    const chartData = details?.monthly_dynamics?.map(item => ({
        month: new Date(item.month).toLocaleDateString('ru', { month: 'short', year: '2-digit' }),
        quantity: item.quantity,
        revenue: item.revenue,
    })) || [];

    const sortedShipments = [...(details?.shipments_history || [])].sort((a, b) => {
        const d = new Date(b.date) - new Date(a.date);
        return d !== 0 ? d : b.number.localeCompare(a.number, undefined, { numeric: true });
    });

    return (
        <ModalShell open={visible} onClose={onClose} maxWidth={1000}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, minWidth: 0 }}>
                        <h2 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0, lineHeight: 1.2 }}>{product?.name}</h2>
                        {product?.subgroup && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>{product.subgroup}</span>}
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
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12 }}>
                                    <StatCard size={24} title="Отгрузок" value={fmt(details.statistics.total_shipments)} />
                                    <StatCard size={24} title="Продано" value={`${fmt(details.statistics.total_quantity)} шт.`} />
                                    <StatCard size={24} title="Среднее в отгрузке" value={`${fmt(details.statistics.average_quantity)} шт.`} />
                                    <StatCard size={24} title="Выручка" value={fmtRub(details.statistics.total_revenue)} />
                                </div>
                            </div>

                            {/* Chart */}
                            {chartData.length > 0 && (
                                <div>
                                    <SectionLabel>Динамика по месяцам</SectionLabel>
                                    <div style={{ height: 260 }}>
                                        <ResponsiveContainer width="100%" height="100%">
                                            <LineChart data={chartData} margin={{ top: 4, right: 48, left: 0, bottom: 0 }}>
                                                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
                                                <XAxis dataKey="month" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} />
                                                <YAxis yAxisId="qty" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} tickFormatter={fmt} width={50} />
                                                <YAxis yAxisId="rev" orientation="right" tick={{ fontFamily: 'var(--sans)', fontSize: 11, fill: 'var(--muted)' }} tickFormatter={v => `${(v / 1000).toFixed(0)}k`} width={44} />
                                                <Tooltip content={<ChartTooltip />} />
                                                <Line {...CHART_ANIMATION} yAxisId="qty" type="monotone" dataKey="quantity" name="Количество" stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: 'var(--primary)' }} activeDot={{ r: 5 }} />
                                                <Line {...CHART_ANIMATION} yAxisId="rev" type="monotone" dataKey="revenue" name="Выручка" stroke="#5a8a6a" strokeWidth={2} dot={{ r: 3, fill: '#5a8a6a' }} activeDot={{ r: 5 }} />
                                            </LineChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Materials + shipments */}
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: 20 }}>
                                {/* Materials */}
                                <div>
                                    <SectionLabel>Используемые материалы</SectionLabel>
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        {details.materials?.map((m, i) => (
                                            <div key={i} style={{ background: 'var(--surface-card)', borderRadius: 10, padding: '10px 14px', border: '1px solid var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)' }}>{m.name}</span>
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', whiteSpace: 'nowrap', marginLeft: 12 }}>{fmt(m.quantity)} {m.unit}</span>
                                            </div>
                                        ))}
                                        {!details.materials?.length && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет данных</span>}
                                    </div>
                                </div>

                                {/* Shipments history */}
                                <div>
                                    <SectionLabel>История отгрузок</SectionLabel>
                                    <div style={{ maxHeight: 400, overflowY: 'auto' }}>
                                        {sortedShipments.map((s, i) => (
                                            <ShipmentRow key={`${s.number}-${i}`} shipment={s} />
                                        ))}
                                        {!sortedShipments.length && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет истории</span>}
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
        </ModalShell>
    );
};

ProductDetailsModal.propTypes = {
    product: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string, subgroup: PropTypes.string }),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    dateRange: PropTypes.shape({ startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default ProductDetailsModal;
