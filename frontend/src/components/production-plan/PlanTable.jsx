import PropTypes from 'prop-types';
import { Badge, DataTable, Hint } from '../ui';
import { FadeRise } from '../ui/motion';
import Breakdown from './Breakdown';
import { HINTS, STATUS, days, monthShort, qty } from './format';

const head = (label, note, hint) => (
    <span className="plan-head">
        <span className="plan-head__label">{label}{hint && <Hint text={hint} />}</span>
        {note && <small>{note}</small>}
    </span>
);

const columns = (months) => [
    { key: 'article', label: 'Артикул', className: 'plan-code' },
    { key: 'name', label: head('Название', null, HINTS.name), render: (row) => <>{row.green && <span className="plan-green" title="Зелёный список" />}{row.name}</> },
    ...months.map((month, i) => ({
        key: month,
        label: i === months.length - 1 ? head(monthShort(month), null, HINTS.months) : monthShort(month),
        numeric: true,
        className: 'is-muted',
        render: (row) => (row.spikes.includes(i)
            ? <span className="plan-spike" title="Всплеск, в расчёт не взят">{qty(row.months[i])} ↑</span>
            : qty(row.months[i])),
    })),
    { key: 'usual', label: head('Обычно в мес', 'середина из 3', HINTS.usual), numeric: true, className: 'is-accent', render: (row) => qty(row.usual) },
    { key: 'need', label: head('Нужно', 'на 2 мес', HINTS.need), numeric: true, render: (row) => qty(row.need) },
    { key: 'available', label: head('Можно взять', 'склад − резерв', HINTS.available), numeric: true, render: (row) => (row.available ? qty(row.available) : <span className="is-zero">0</span>) },
    { key: 'days', label: head('Хватит на', 'склада', HINTS.days), numeric: true, render: (row) => <span className={row.status === 'urgent' ? 'is-zero' : ''}>{days(row.days)}</span> },
    { key: 'in_production', label: head('В производстве', 'по заданиям', HINTS.inProduction), numeric: true, className: 'is-muted', render: (row) => qty(row.in_production) },
    { key: 'produce', label: head('Произвести', null, HINTS.produce), numeric: true, className: 'is-accent plan-produce', render: (row) => qty(row.produce) },
    { key: 'status', label: head('Статус', null, HINTS.status), render: (row) => <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge> },
];

export default function PlanTable({ rows, months, loading, emptyText, onToggleGreen }) {
    return (
        <div className="plan-table">
            <DataTable
                columns={columns(months)}
                rows={rows}
                rowKey="article"
                loading={loading}
                skeletonRows={10}
                emptyText={emptyText}
                renderExpanded={(row) => <FadeRise><Breakdown row={row} months={months} onToggleGreen={onToggleGreen} /></FadeRise>}
            />
        </div>
    );
}

PlanTable.propTypes = {
    rows: PropTypes.array.isRequired,
    months: PropTypes.arrayOf(PropTypes.string).isRequired,
    loading: PropTypes.bool,
    emptyText: PropTypes.string,
    onToggleGreen: PropTypes.func.isRequired,
};
