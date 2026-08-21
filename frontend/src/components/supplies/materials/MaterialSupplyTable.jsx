import { useCallback } from 'react';
import { num, pluralWith } from '../../../utils/formatters';
import PropTypes from 'prop-types';
import { Eye, Loader2 } from 'lucide-react';
import { Badge, Button, Card, DataTable, Metric, MetricGrid } from '../../ui';
import { useRowDetails } from '../../../hooks/useRowDetails';
import { suppliesApi } from '../../../api/suppliesApi';


/** Карточка поставщика внутри раскрытой строки материала. */
const SupplierInfo = ({ supplier, uom }) => {
    const { min, max } = supplier.price_range;

    return (
        <Card tone="plain" style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 'var(--size-md)', fontWeight: 500, color: 'var(--ink)' }}>{supplier.name}</span>
                <Badge tone="neutral">{pluralWith(supplier.total_supplies, 'поставка', 'поставки', 'поставок')}</Badge>
            </div>

            <MetricGrid>
                <Metric label="Количество" value={`${num(supplier.total_quantity)} ${uom}`} />
                <Metric label="Сумма" value={`${num(supplier.total_sum)} ₽`} />
                <Metric
                    label="Диапазон цен"
                    value={min === max ? `${min.toFixed(2)} ₽` : `${min.toFixed(2)}–${max.toFixed(2)} ₽`}
                />
                <Metric
                    label="Средняя цена"
                    value={supplier.total_quantity
                        ? `${(supplier.total_sum / supplier.total_quantity).toFixed(2)} ₽/${uom}`
                        : '—'}
                />
            </MetricGrid>
        </Card>
    );
};

SupplierInfo.propTypes = {
    supplier: PropTypes.shape({
        name: PropTypes.string.isRequired,
        total_supplies: PropTypes.number.isRequired,
        total_quantity: PropTypes.number.isRequired,
        total_sum: PropTypes.number.isRequired,
        price_range: PropTypes.shape({ min: PropTypes.number.isRequired, max: PropTypes.number.isRequired }).isRequired,
    }).isRequired,
    uom: PropTypes.string.isRequired,
};

const columns = (onMaterialClick) => [
    { key: 'name', label: 'Наименование', strong: true },
    {
        key: 'code',
        label: 'Код',
        render: (r) => <span style={{ fontFamily: 'var(--mono)', fontSize: 'var(--size-sm)' }}>{r.code}</span>,
    },
    { key: 'group', label: 'Группа' },
    { key: 'total_quantity', label: 'Количество', numeric: true, render: (r) => `${num(r.total_quantity)} ${r.uom}` },
    { key: 'average_price', label: 'Средняя цена', numeric: true, render: (r) => `${(r.average_price || 0).toFixed(2)} ₽/${r.uom}` },
    { key: 'total_sum', label: 'Сумма', numeric: true, render: (r) => `${num(r.total_sum)} ₽` },
    {
        key: 'details',
        label: 'Детали',
        sortable: false,
        render: (row) => (
            <Button variant="link" size="sm" icon={Eye} onClick={() => onMaterialClick(row)}>
                Детали
            </Button>
        ),
    },
];

const MaterialSupplyTable = ({ materials, loading, pagination, sortField, sortOrder, onSort, onPageChange, onMaterialClick, filters }) => {
    // Детали считаются за выбранный период, поэтому он входит в ключ кэша
    const cacheKey = useCallback((id) => {
        const f = filters || {};
        return `${id}:${f.startDate || ''}:${f.endDate || ''}`;
    }, [filters]);

    const fetchFn = useCallback((id) => {
        const params = new URLSearchParams();
        if (filters?.startDate) params.append('startDate', filters.startDate);
        if (filters?.endDate) params.append('endDate', filters.endDate);
        return suppliesApi.materials.getDetails(id, params.toString());
    }, [filters]);

    const { load, get, isLoading } = useRowDetails({ fetchFn, cacheKey });

    const renderExpanded = (row) => {
        if (isLoading(row.id)) {
            return (
                <div style={{ textAlign: 'center', color: 'var(--muted)', padding: '8px 0' }}>
                    <Loader2 size={14} className="animate-spin" style={{ display: 'inline-block' }} />
                </div>
            );
        }

        const suppliers = get(row.id)?.suppliers;
        if (!suppliers?.length) {
            return <span style={{ fontSize: 'var(--size-sm)', color: 'var(--muted)' }}>Нет данных о поставщиках</span>;
        }

        return (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                {suppliers.map((s, i) => <SupplierInfo key={`${row.id}-${i}`} supplier={s} uom={row.uom} />)}
            </div>
        );
    };

    return (
        <DataTable
            columns={columns(onMaterialClick)}
            rows={materials}
            loading={loading}
            sortField={sortField}
            sortOrder={sortOrder}
            onSort={onSort}
            pagination={pagination}
            onPageChange={onPageChange}
            onExpand={(row) => load(row.id)}
            renderExpanded={renderExpanded}
        />
    );
};

MaterialSupplyTable.propTypes = {
    materials: PropTypes.array.isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onMaterialClick: PropTypes.func.isRequired,
    filters: PropTypes.shape({ search: PropTypes.string, group: PropTypes.string, startDate: PropTypes.string, endDate: PropTypes.string }),
};

export default MaterialSupplyTable;
