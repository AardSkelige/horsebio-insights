import { useCallback, useState } from 'react';
import { num, pluralWith } from '../../../utils/formatters';
import PropTypes from 'prop-types';
import { ChevronRight, Eye, Loader2 } from 'lucide-react';
import { MaterialPropTypes, FiltersPropTypes } from './types';
import { Badge, Button, Card, DataTable, Metric, MetricGrid } from '../../ui';
import { useRowDetails } from '../../../hooks/useRowDetails';
import { materialsApi } from '../../../api/materialsApi';


/** Карточка поставщика внутри раскрытой строки материала. */
const SupplierInfo = ({ supplier, uom }) => {
    const [open, setOpen] = useState(false);

    // Диапазон приходит с бэкенда, но у части материалов он нулевой —
    // тогда собираем его из последних поставок
    const priceRange = supplier.price_range?.some((p) => p !== 0)
        ? supplier.price_range
        : supplier.last_supplies?.length
            ? [
                Math.min(...supplier.last_supplies.map((s) => s.price)),
                Math.max(...supplier.last_supplies.map((s) => s.price)),
            ]
            : null;
    const hasRange = priceRange && priceRange[0] !== priceRange[1];

    return (
        <Card tone="plain" style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 'var(--size-md)', fontWeight: 500, color: 'var(--ink)' }}>{supplier.name}</span>
                <Badge tone="neutral">{pluralWith(supplier.total_supplies, 'поставка', 'поставки', 'поставок')}</Badge>
            </div>

            <MetricGrid style={{ marginBottom: 6 }}>
                <Metric label="Средняя цена" value={`${(supplier.avg_price || 0).toFixed(2)} ₽/${uom}`} />
                <Metric
                    label="Диапазон цен"
                    value={hasRange
                        ? `${priceRange[0].toFixed(2)}–${priceRange[1].toFixed(2)} ₽`
                        : `${(supplier.avg_price || 0).toFixed(2)} ₽`}
                />
                <Metric label="Всего" value={`${num(supplier.total_quantity)} ${uom}`} />
            </MetricGrid>

            {supplier.last_supplies?.length > 0 && (
                <>
                    <Button variant="quiet" size="sm" onClick={() => setOpen((o) => !o)}>
                        <ChevronRight size={11} className={`ui-table__chevron${open ? ' is-open' : ''}`} aria-hidden="true" />
                        Последние поставки
                    </Button>
                    {open && (
                        <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
                            {supplier.last_supplies.map((s, i) => (
                                <div
                                    key={i}
                                    style={{
                                        background: 'var(--surface-card)', borderRadius: 'var(--radius-sm)',
                                        padding: '5px 8px', display: 'flex', justifyContent: 'space-between',
                                        gap: 8, fontSize: 'var(--size-xs)',
                                    }}
                                >
                                    <span style={{ color: 'var(--muted)' }}>{s.date}</span>
                                    <span style={{ color: 'var(--ink)' }}>{s.price.toFixed(2)} ₽ · {num(s.quantity)} {uom}</span>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
        </Card>
    );
};

SupplierInfo.propTypes = {
    supplier: PropTypes.shape({
        name: PropTypes.string.isRequired,
        total_supplies: PropTypes.number.isRequired,
        total_quantity: PropTypes.number,
        avg_price: PropTypes.number,
        price_range: PropTypes.arrayOf(PropTypes.number),
        last_supplies: PropTypes.arrayOf(PropTypes.shape({ date: PropTypes.string, quantity: PropTypes.number, price: PropTypes.number })),
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
    { key: 'total_usage', label: 'Количество', numeric: true, render: (r) => `${num(r.total_usage)} ${r.uom}` },
    { key: 'shipments_count', label: 'Отгрузки', numeric: true, render: (r) => num(r.shipments_count) },
    { key: 'suppliers_count', label: 'Поставщики', render: (r) => r.suppliers_count ? pluralWith(r.suppliers_count, 'поставщик', 'поставщика', 'поставщиков') : '—' },
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

const MaterialTable = ({ materials, loading, pagination, sortField, sortOrder, onSort, onPageChange, onMaterialClick, filters }) => {
    // Детали зависят от периода и списка контрагентов, поэтому фильтры входят в ключ кэша
    const cacheKey = useCallback((id) => {
        const f = filters || {};
        return `${id}:${f.startDate || ''}:${f.endDate || ''}:${(f.counterparties || []).join(',')}`;
    }, [filters]);

    const fetchFn = useCallback((id) => {
        const params = new URLSearchParams();
        if (filters?.startDate) params.append('startDate', filters.startDate);
        if (filters?.endDate) params.append('endDate', filters.endDate);
        filters?.counterparties?.forEach((c) => params.append('counterparties', c));
        return materialsApi.getDetails(id, params.toString());
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

MaterialTable.propTypes = {
    materials: PropTypes.arrayOf(PropTypes.shape(MaterialPropTypes)).isRequired,
    loading: PropTypes.bool.isRequired,
    pagination: PropTypes.shape({ current: PropTypes.number, pageSize: PropTypes.number, total: PropTypes.number }).isRequired,
    sortField: PropTypes.string.isRequired,
    sortOrder: PropTypes.string.isRequired,
    onSort: PropTypes.func.isRequired,
    onPageChange: PropTypes.func.isRequired,
    onMaterialClick: PropTypes.func.isRequired,
    filters: PropTypes.shape(FiltersPropTypes),
};

export default MaterialTable;
