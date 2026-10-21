import PropTypes from 'prop-types';
import { Badge, DataTable } from '../ui';
import { FadeRise } from '../ui/motion';
import Breakdown from './Breakdown';
import { STATUS, monthShort, qty } from './format';

const head = (label, hint) => <span className="plan-head">{label}<small>{hint}</small></span>;

const columns = (months) => [
    { key: 'article', label: 'Артикул', className: 'plan-code' },
    { key: 'name', label: 'Название', render: (row) => <>{row.green && <span className="plan-green" title="Зелёный список" />}{row.name}</> },
    ...months.map((month, i) => ({
        key: month,
        label: monthShort(month),
        numeric: true,
        className: 'is-muted',
        render: (row) => (row.spikes.includes(i)
            ? <span className="plan-spike" title="Всплеск, в расчёт не взят">{qty(row.months[i])} ↑</span>
            : qty(row.months[i])),
    })),
    { key: 'usual', label: head('Обычно в мес', 'середина из 3'), numeric: true, className: 'is-accent', render: (row) => qty(row.usual) },
    { key: 'need', label: head('Нужно', 'на 2 мес'), numeric: true, render: (row) => qty(row.need) },
    { key: 'available', label: head('Можно взять', 'склад − резерв'), numeric: true, render: (row) => (row.available ? qty(row.available) : <span className="is-zero">0</span>) },
    { key: 'in_production', label: head('В производстве', 'по заданиям'), numeric: true, className: 'is-muted', render: (row) => qty(row.in_production) },
    { key: 'produce', label: 'Произвести', numeric: true, className: 'is-accent plan-produce', render: (row) => qty(row.produce) },
    { key: 'status', label: 'Статус', render: (row) => <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge> },
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
