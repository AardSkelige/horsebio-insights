import PropTypes from 'prop-types';
import { num } from '../../utils/formatters';
import { useMemo, useState } from 'react';
import { DataTable } from '../ui';


/**
 * Сводка по товарам в FBO-заказах.
 *
 * Сортировка здесь клиентская: список приходит целиком, страниц нет.
 * Оформление берёт общая таблица — раньше у этой были свои заголовки и ячейки,
 * из-за чего она заметно отличалась от остальных списков приложения.
 */
const columns = [
    { key: 'name', label: 'Наименование', strong: true },
    { key: 'fbo_quantity', label: 'FBO заказ', numeric: true, render: (r) => num(r.fbo_quantity) },
    { key: 'stock', label: 'Остаток', numeric: true, render: (r) => num(r.stock) },
    { key: 'sales_30_days', label: 'Продажи', numeric: true, render: (r) => num(r.sales_30_days) },
    {
        key: 'production_needed',
        label: 'Нужно произвести',
        numeric: true,
        // Положительное значение — дефицит, его и подсвечиваем
        render: (r) => (
            <span style={{ color: r.production_needed > 0 ? 'var(--error-ink)' : 'var(--success-ink)', fontWeight: 500 }}>
                {num(r.production_needed)}
            </span>
        ),
    },
];

const FBOTable = ({ products }) => {
    const [sort, setSort] = useState({ key: 'fbo_quantity', dir: 'desc' });

    const sorted = useMemo(() => [...products].sort((a, b) => {
        const av = a[sort.key];
        const bv = b[sort.key];
        const result = typeof av === 'number' && typeof bv === 'number'
            ? av - bv
            : String(av ?? '').localeCompare(String(bv ?? ''), 'ru');
        return sort.dir === 'asc' ? result : -result;
    }), [products, sort]);

    const handleSort = (key) => setSort((prev) => ({
        key,
        dir: prev.key === key && prev.dir === 'asc' ? 'desc' : 'asc',
    }));

    return (
        <DataTable
            columns={columns}
            rows={sorted}
            rowKey="name"
            sortField={sort.key}
            sortOrder={sort.dir}
            onSort={handleSort}
            emptyText="Нет данных для отображения"
        />
    );
};

FBOTable.propTypes = {
    products: PropTypes.arrayOf(PropTypes.shape({
        name: PropTypes.string.isRequired,
        fbo_quantity: PropTypes.number.isRequired,
        stock: PropTypes.number.isRequired,
        sales_30_days: PropTypes.number.isRequired,
        production_needed: PropTypes.number.isRequired,
    })).isRequired,
};

export default FBOTable;
