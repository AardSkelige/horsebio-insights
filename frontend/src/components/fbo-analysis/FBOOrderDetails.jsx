import PropTypes from 'prop-types';
import { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { formatDate } from '../../utils/formatters';

const FBOOrderDetails = ({ orders }) => {
    const [expanded, setExpanded] = useState(new Set());

    const toggle = (id) => {
        const next = new Set(expanded);
        next.has(id) ? next.delete(id) : next.add(id);
        setExpanded(next);
    };

    if (orders.length === 0) return (
        <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', textAlign: 'center', padding: '32px 0' }}>
            Нет заказов для отображения
        </p>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {orders.map((order) => {
                const isOpen = expanded.has(order.id);
                return (
                    <div key={order.id} style={{ border: `1px solid ${isOpen ? 'var(--primary)' : 'var(--hairline)'}`, borderRadius: '10px', overflow: 'hidden', transition: 'border-color 150ms ease' }}>
                        <div
                            onClick={() => toggle(order.id)}
                            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', cursor: 'pointer', backgroundColor: 'var(--canvas)', userSelect: 'none' }}
                            onMouseEnter={e => !isOpen && (e.currentTarget.style.backgroundColor = 'var(--surface-card)')}
                            onMouseLeave={e => !isOpen && (e.currentTarget.style.backgroundColor = 'var(--canvas)')}
                        >
                            <div>
                                <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>
                                    Заказ {order.name}
                                </span>
                                <span style={{ fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted)', marginLeft: '10px' }}>
                                    {formatDate(order.delivery_date, true)}
                                </span>
                            </div>
                            {isOpen
                                ? <ChevronUp style={{ width: 15, height: 15, color: 'var(--muted)', flexShrink: 0 }} />
                                : <ChevronDown style={{ width: 15, height: 15, color: 'var(--muted)', flexShrink: 0 }} />
                            }
                        </div>

                        {isOpen && (
                            <div style={{ borderTop: '1px solid var(--hairline)', padding: '16px', backgroundColor: 'var(--surface-card)', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                        {[
                                            { label: 'Дата создания',   value: formatDate(order.created_date, true) },
                                            { label: 'Контрагент',      value: order.contractor },
                                            { label: 'Статус',          value: order.status },
                                        ].map(({ label, value }) => (
                                            <div key={label}>
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '2px' }}>{label}</span>
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>{value}</span>
                                            </div>
                                        ))}
                                    </div>
                                    <div style={{ backgroundColor: 'var(--canvas)', borderRadius: '8px', border: '1px solid var(--hairline)', padding: '12px' }}>
                                        <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>Плановая дата отгрузки</span>
                                        <span style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--primary)' }}>
                                            {formatDate(order.delivery_date, true)}
                                        </span>
                                    </div>
                                </div>

                                {order.details && (
                                    <div style={{ backgroundColor: 'var(--canvas)', borderRadius: '8px', border: '1px solid var(--hairline)', padding: '12px' }}>
                                        <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>Дополнительная информация</span>
                                        <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)', margin: 0 }}>{order.details}</p>
                                    </div>
                                )}

                                <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted-soft)' }}>ID: {order.id}</span>
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
};

FBOOrderDetails.propTypes = {
    orders: PropTypes.arrayOf(PropTypes.shape({
        id: PropTypes.string.isRequired,
        name: PropTypes.string.isRequired,
        created_date: PropTypes.string.isRequired,
        delivery_date: PropTypes.string.isRequired,
        status: PropTypes.string.isRequired,
        contractor: PropTypes.string.isRequired,
        details: PropTypes.string,
    })).isRequired,
};

export default FBOOrderDetails;
