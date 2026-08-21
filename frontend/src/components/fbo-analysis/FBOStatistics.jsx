import PropTypes from 'prop-types';
import { Package, TruckIcon } from 'lucide-react';
import { Notice, StatCard, StatGrid } from '../ui';
import { formatDate, num } from '../../utils/formatters';


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

            <StatGrid>
                {cards.map(({ title, value, Icon }) => (
                    <StatCard key={title} tone="dark" icon={Icon} title={title} value={num(value)} />
                ))}
            </StatGrid>

            {statistics.no_shipment_orders > 0 && (
                <Notice tone="info">
                    Неотгруженных FBO заказов с датой отгрузки сегодня или позже:{' '}
                    <strong>{num(statistics.no_shipment_orders)}</strong>
                </Notice>
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
