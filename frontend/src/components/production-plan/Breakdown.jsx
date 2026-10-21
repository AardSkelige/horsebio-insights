import PropTypes from 'prop-types';
import { Button } from '../ui';
import { monthIn, monthName, qty } from './format';

export default function Breakdown({ row, months, onToggleGreen }) {
    const spikes = row.spikes.map((i) => `в ${monthIn(months[i])} ${qty(row.months[i])}`);
    return (
        <div className="plan-breakdown">
            <div className="plan-breakdown__title">Продажи по каналам, шт</div>
            <table className="plan-breakdown__table">
                <thead>
                    <tr>
                        <th>Канал</th>
                        {months.map((month) => <th key={month}>{monthName(month)}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {row.channels.map((channel) => (
                        <tr key={channel.key}>
                            <td>{channel.label}</td>
                            {channel.months.map((value, i) => <td key={months[i]}>{qty(value)}</td>)}
                        </tr>
                    ))}
                    <tr className="plan-breakdown__total">
                        <td>Всего</td>
                        {row.months.map((value, i) => (
                            <td key={months[i]}>
                                {row.spikes.includes(i) ? <span className="plan-spike">{qty(value)} ↑</span> : qty(value)}
                            </td>
                        ))}
                    </tr>
                </tbody>
            </table>
            <p className="plan-breakdown__formula">
                Обычно в месяц — <b>{qty(row.usual)}</b>.
                {spikes.length > 0 && ` Всплеск (${spikes.join(', ')}) в расчёт не взят.`}
                {' '}Нужно на 2 месяца {qty(row.need)} − можно взять {qty(row.available)} − в производстве {qty(row.in_production)} = <b>произвести {qty(row.produce)}</b>.
            </p>
            <Button variant="secondary" size="sm" onClick={() => onToggleGreen(row)}>
                {row.green ? 'Убрать из зелёного списка' : 'Добавить в зелёный список'}
            </Button>
        </div>
    );
}

Breakdown.propTypes = {
    row: PropTypes.object.isRequired,
    months: PropTypes.arrayOf(PropTypes.string).isRequired,
    onToggleGreen: PropTypes.func.isRequired,
};
