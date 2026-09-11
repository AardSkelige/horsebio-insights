import PropTypes from 'prop-types';
import { AlertTriangle, TruckIcon } from 'lucide-react';
import { Notice, StatCard, StatGrid } from '../ui';
import { formatDate, money, num } from '../../utils/formatters';


const FBOStatistics = ({ statistics }) => {
    const overdue = statistics.overdue_orders || 0;

    // «Всего заказов» отсюда убрано: это было число всех заказов покупателей
    // за месяц — розница, сайт, маркетплейсы вперемешку. На странице про
    // отгрузки FBO по нему нельзя было ни найти, ни сделать ничего.
    const cards = [
        { title: 'К отгрузке', value: num(statistics.fbo_orders), Icon: TruckIcon },
        { title: 'Просрочено', value: num(overdue), Icon: AlertTriangle },
    ];

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <StatGrid>
                {cards.map(({ title, value, Icon }) => (
                    <StatCard key={title} tone="dark" icon={Icon} title={title} value={value} />
                ))}
            </StatGrid>

            {overdue > 0 && (
                <Notice tone="warning">
                    Просрочено {num(overdue)} на {money(statistics.overdue_sum)}, самый давний ждёт{' '}
                    {num(statistics.overdue_oldest_days)} дн. — плановая дата прошла, отгрузки нет
                </Notice>
            )}

            <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                Продажи в таблице товаров учтены за {formatDate(statistics.start_date)} — {formatDate(statistics.end_date)}
            </p>
        </div>
    );
};

FBOStatistics.propTypes = {
    statistics: PropTypes.shape({
        fbo_orders: PropTypes.number.isRequired,
        overdue_orders: PropTypes.number,
        overdue_sum: PropTypes.number,
        overdue_oldest_days: PropTypes.number,
        start_date: PropTypes.string.isRequired,
        end_date: PropTypes.string.isRequired
    }).isRequired
};

export default FBOStatistics;
