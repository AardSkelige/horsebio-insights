import PropTypes from 'prop-types';
import { money, num } from '../../../utils/formatters';
import { Eye } from 'lucide-react';
import { CounterpartyPropTypes } from './types';
import { Button, DataTable } from '../../ui';


const columns = (onCounterpartyClick) => [
    { key: 'name', label: 'Контрагент', strong: true },
    { key: 'total_sales', label: 'Сумма продаж', numeric: true, render: (r) => money(r.total_sales) },
    { key: 'shipments_count', label: 'Отгрузок', numeric: true, render: (r) => num(r.shipments_count) },
    { key: 'total_products', label: 'Товаров', numeric: true, render: (r) => num(r.total_products) },
    {
        key: 'last_shipment',
        label: 'Последняя отгрузка',
        render: (r) => r.last_shipment ? new Date(r.last_shipment).toLocaleDateString('ru-RU') : '—',
    },
    {
        key: 'details',
        label: 'Детали',
        sortable: false,
        render: (row) => (
            <Button variant="link" size="sm" icon={Eye} onClick={() => onCounterpartyClick(row)}>
                Детали
            </Button>
        ),
    },
];

const CounterpartyTable = ({ counterparties, loading, pagination, sortField, sortOrder, onSort, onPageChange, onCounterpartyClick }) => (
    <DataTable
        columns={columns(onCounterpartyClick)}
        rows={counterparties}
        loading={loading}
        sortField={sortField}
        sortOrder={sortOrder}
        onSort={onSort}
        pagination={pagination}
        onPageChange={onPageChange}
    />
);

CounterpartyTable.propTypes = {
    counterparties: PropTypes.arrayOf(PropTypes.shape(CounterpartyPropTypes)).isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onCounterpartyClick: PropTypes.func.isRequired,
};

export default CounterpartyTable;
