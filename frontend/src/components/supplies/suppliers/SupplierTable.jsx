import PropTypes from 'prop-types';
import { num } from '../../../utils/formatters';
import { Eye } from 'lucide-react';
import { SupplierPropTypes } from './types';
import { Button, DataTable } from '../../ui';

const fmtDate = (d) => d ? new Date(d).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';

const columns = (onSupplierClick) => [
    { key: 'name', label: 'Наименование', strong: true },
    { key: 'supplies_count', label: 'Приёмок', numeric: true, render: (r) => num(r.supplies_count) },
    { key: 'positions_count', label: 'Позиции', numeric: true, render: (r) => num(r.positions_count) },
    { key: 'unique_materials', label: 'Материалов', numeric: true, render: (r) => num(r.unique_materials) },
    { key: 'total_sum', label: 'Общая сумма', numeric: true, render: (r) => `${num(r.total_sum)} ₽` },
    { key: 'avg_supply_sum', label: 'Средняя сумма', numeric: true, render: (r) => `${num(r.avg_supply_sum)} ₽` },
    { key: 'last_supply', label: 'Последняя приёмка', render: (r) => fmtDate(r.last_supply) },
    {
        key: 'details',
        label: 'Детали',
        sortable: false,
        render: (row) => (
            <Button variant="link" size="sm" icon={Eye} onClick={() => onSupplierClick(row)}>
                Детали
            </Button>
        ),
    },
];

const SupplierTable = ({ suppliers, loading, pagination, sortField, sortOrder, onSort, onPageChange, onSupplierClick }) => (
    <DataTable
        columns={columns(onSupplierClick)}
        rows={suppliers}
        loading={loading}
        sortField={sortField}
        sortOrder={sortOrder}
        onSort={onSort}
        pagination={pagination}
        onPageChange={onPageChange}
    />
);

SupplierTable.propTypes = {
    suppliers: PropTypes.arrayOf(PropTypes.shape(SupplierPropTypes)).isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onSupplierClick: PropTypes.func.isRequired,
};

export default SupplierTable;
