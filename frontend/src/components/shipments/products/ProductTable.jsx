import PropTypes from 'prop-types';
import { money, moneyPrecise, num } from '../../../utils/formatters';
import { Eye } from 'lucide-react';
import { ProductPropTypes } from './types';
import { Button, DataTable } from '../../ui';


const columns = (onProductClick) => [
    {
        key: 'name',
        label: 'Товар',
        strong: true,
        // Подгруппа поясняет одноимённые товары, поэтому идёт второй строкой в той же ячейке
        render: (row) => (
            <div style={{ maxWidth: 280 }}>
                <div>{row.name}</div>
                {row.subgroup && (
                    <div style={{ fontSize: 'var(--size-xs)', color: 'var(--muted)', marginTop: 2 }}>
                        {row.subgroup}
                    </div>
                )}
            </div>
        ),
    },
    { key: 'quantity', label: 'Количество', numeric: true, render: (r) => num(r.quantity) },
    { key: 'average_price', label: 'Средняя цена', numeric: true, render: (r) => moneyPrecise(r.average_price) },
    { key: 'total_sum', label: 'Сумма продаж', numeric: true, render: (r) => money(r.total_sum) },
    { key: 'shipments_count', label: 'Отгрузок', numeric: true, render: (r) => num(r.shipments_count) },
    {
        key: 'details',
        label: 'Детали',
        sortable: false,
        render: (row) => (
            <Button variant="link" size="sm" icon={Eye} onClick={() => onProductClick(row)}>
                Детали
            </Button>
        ),
    },
];

const ProductTable = ({ products, loading, pagination, sortField, sortOrder, onSort, onPageChange, onProductClick }) => (
    <DataTable
        columns={columns(onProductClick)}
        rows={products}
        loading={loading}
        sortField={sortField}
        sortOrder={sortOrder}
        onSort={onSort}
        pagination={pagination}
        onPageChange={onPageChange}
    />
);

ProductTable.propTypes = {
    products: PropTypes.arrayOf(PropTypes.shape(ProductPropTypes)).isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onProductClick: PropTypes.func.isRequired,
};

export default ProductTable;
