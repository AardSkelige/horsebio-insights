import PropTypes from 'prop-types';
import { Package, TruckIcon } from 'lucide-react';
import { formatDate } from '../../utils/formatters';

const fmt = (n) => new Intl.NumberFormat('ru-RU').format(n);

const FBOStatistics = ({ statistics }) => {
    const cards = [
        { title: 'Всего заказов', value: statistics.total_orders, Icon: Package },
        { title: 'FBO заказов',   value: statistics.fbo_orders,   Icon: TruckIcon },
    ];

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                Период анализа: {formatDate(statistics.start_date)} — {formatDate(statistics.end_date)}
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {cards.map(({ title, value, Icon }) => (
                    <div key={title} style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '12px', padding: '20px', display: 'flex', alignItems: 'center', gap: '16px' }}>
                        <div style={{ width: '36px', height: '36px', borderRadius: '8px', backgroundColor: 'var(--surface-dark-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Icon style={{ width: 16, height: 16, color: 'var(--primary)' }} />
                        </div>
                        <div>
                            <p style={{ fontFamily: 'var(--sans)', fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--on-dark-soft)', margin: 0, marginBottom: '4px' }}>
                                {title}
                            </p>
                            <p style={{ fontFamily: 'var(--serif)', fontSize: '28px', fontWeight: 400, letterSpacing: '-0.02em', lineHeight: 1, color: 'var(--on-dark)', margin: 0, fontVariantNumeric: 'lining-nums' }}>
                                {fmt(value)}
                            </p>
                        </div>
                    </div>
                ))}
            </div>

            {statistics.no_shipment_orders > 0 && (
                <div style={{ backgroundColor: 'rgba(204,120,92,0.08)', border: '1px solid rgba(204,120,92,0.2)', borderRadius: '10px', padding: '12px 16px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <Package style={{ width: 15, height: 15, color: 'var(--primary)', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>
                        Неотгруженных FBO заказов с датой отгрузки сегодня или позже:{' '}
                        <strong>{fmt(statistics.no_shipment_orders)}</strong>
                    </span>
                </div>
            )}
        </div>
    );
};

FBOStatistics.propTypes = {
    statistics: PropTypes.shape({
        total_orders: PropTypes.number.isRequired,
        fbo_orders: PropTypes.number.isRequired,
        no_shipment_orders: PropTypes.number.isRequired,
        start_date: PropTypes.string.isRequired,
        end_date: PropTypes.string.isRequired
    }).isRequired
};

export default FBOStatistics;
