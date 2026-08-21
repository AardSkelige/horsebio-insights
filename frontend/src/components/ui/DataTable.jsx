import { Fragment, useState } from 'react';
import PropTypes from 'prop-types';
import { ChevronDown, ChevronRight, ChevronsUpDown, ChevronUp } from 'lucide-react';
import { SkeletonRows } from './Skeleton';
import { useRowHoverPill } from './motion';
import Pagination from './Pagination';

/**
 * Таблица с сортировкой, скелетоном загрузки, пустым состоянием и пагинацией.
 *
 * Колонки описываются данными, а не разметкой:
 *
 *   const COLUMNS = [
 *     { key: 'name',      label: 'Наименование', strong: true },
 *     { key: 'total_sum', label: 'Сумма', numeric: true, render: (row) => fmt(row.total_sum) },
 *     { key: 'details',   label: 'Детали', sortable: false, render: (row) => <Button .../> },
 *   ];
 *
 * Пять таблиц разделов «Отгрузки» и «Приёмка» отличались друг от друга только этим
 * списком — всё остальное (оформление заголовков, сортировка, пагинация со свёрткой
 * страниц, скелетон) было скопировано построчно.
 *
 * `renderExpanded` включает раскрывающиеся строки: слева появляется колонка-шеврон,
 * клик по строке разворачивает панель под ней. Подгрузку содержимого удобно вести
 * через `useRowDetails` — он же отдаёт готовый `onExpand`.
 *
 * `onRowClick` делает строку выбираемой (список месяцев, выбор периода),
 * а `isRowActive` подсвечивает выбранную.
 */
export default function DataTable({
    columns,
    rows,
    rowKey = 'id',
    loading = false,
    sortField,
    sortOrder,
    onSort,
    pagination,
    onPageChange,
    emptyText = 'Нет данных',
    skeletonRows = 8,
    renderExpanded,
    onExpand,
    onRowClick,
    isRowActive,
}) {
    const { containerProps, rowHoverProps, pill } = useRowHoverPill();
    const [expandedKeys, setExpandedKeys] = useState([]);

    const keyOf = (row, index) => (typeof rowKey === 'function' ? rowKey(row) : row[rowKey] ?? index);
    const expandable = Boolean(renderExpanded);
    const columnCount = columns.length + (expandable ? 1 : 0);

    const toggle = async (row, key) => {
        if (expandedKeys.includes(key)) {
            setExpandedKeys((prev) => prev.filter((k) => k !== key));
            return;
        }
        // Данные подтягиваем до раскрытия — иначе панель мигает пустотой
        if (onExpand) await onExpand(row);
        setExpandedKeys((prev) => [...prev, key]);
    };

    return (
        <div>
            <div {...containerProps} className="ui-table-wrap">
                {pill}
                <table className="ui-table">
                    <thead>
                        <tr>
                            {expandable && <th className="ui-table__expander-head" />}
                            {columns.map((col) => {
                                const sortable = col.sortable !== false && Boolean(onSort);
                                const sorted = sortField === col.key;
                                return (
                                    <th
                                        key={col.key}
                                        className={[
                                            sortable ? 'is-sortable' : '',
                                            sorted ? 'is-sorted' : '',
                                            col.numeric ? 'is-numeric' : '',
                                        ].filter(Boolean).join(' ')}
                                        onClick={sortable ? () => onSort(col.key) : undefined}
                                        aria-sort={sorted ? (sortOrder === 'asc' ? 'ascending' : 'descending') : undefined}
                                    >
                                        <span className={`ui-table__head-cell${col.numeric ? ' is-numeric' : ''}`}>
                                            {col.label}
                                            {sortable && <SortIcon active={sorted} order={sortOrder} />}
                                        </span>
                                    </th>
                                );
                            })}
                        </tr>
                    </thead>

                    {/* Данные не исчезают на время подгрузки — приглушаются.
                        Скелетон показываем только когда показывать ещё нечего. */}
                    <tbody className={loading && rows.length > 0 ? 'ui-table__body--loading' : undefined}>
                        {loading && rows.length === 0 ? (
                            <SkeletonRows cols={columnCount} rows={skeletonRows} />
                        ) : rows.length === 0 ? (
                            <tr>
                                <td colSpan={columnCount} style={{ textAlign: 'center', padding: '32px 0', color: 'var(--muted)' }}>
                                    {emptyText}
                                </td>
                            </tr>
                        ) : rows.map((row, index) => {
                            const key = keyOf(row, index);
                            const expanded = expandedKeys.includes(key);

                            return (
                                <Fragment key={key}>
                                    <tr
                                        {...rowHoverProps}
                                        className={[
                                            expanded ? 'is-expanded' : '',
                                            isRowActive?.(row) ? 'is-active' : '',
                                        ].filter(Boolean).join(' ') || undefined}
                                        onClick={
                                            expandable ? () => toggle(row, key)
                                                : onRowClick ? () => onRowClick(row)
                                                    : undefined
                                        }
                                        style={expandable || onRowClick ? { cursor: 'pointer' } : undefined}
                                    >
                                        {expandable && (
                                            <td className="ui-table__expander">
                                                <ChevronRight
                                                    size={13}
                                                    className={`ui-table__chevron${expanded ? ' is-open' : ''}`}
                                                    aria-hidden="true"
                                                />
                                            </td>
                                        )}
                                        {columns.map((col) => (
                                            <td
                                                key={col.key}
                                                className={[
                                                    col.numeric ? 'is-numeric' : '',
                                                    col.strong ? 'is-strong' : '',
                                                ].filter(Boolean).join(' ') || undefined}
                                                // Действие внутри ячейки не должно сворачивать строку
                                                onClick={expandable && col.sortable === false ? (e) => e.stopPropagation() : undefined}
                                            >
                                                {col.render ? col.render(row) : row[col.key]}
                                            </td>
                                        ))}
                                    </tr>

                                    {expanded && (
                                        <tr>
                                            <td colSpan={columnCount} className="ui-table__expanded">
                                                {renderExpanded(row)}
                                            </td>
                                        </tr>
                                    )}
                                </Fragment>
                            );
                        })}
                    </tbody>
                </table>
            </div>

            {pagination && onPageChange && (
                <Pagination pagination={pagination} onPageChange={onPageChange} />
            )}
        </div>
    );
}

function SortIcon({ active, order }) {
    if (!active) {
        return <ChevronsUpDown size={11} className="ui-table__sort-icon ui-table__sort-icon--idle" aria-hidden="true" />;
    }
    const Icon = order === 'asc' ? ChevronUp : ChevronDown;
    return <Icon size={11} className="ui-table__sort-icon" aria-hidden="true" />;
}

SortIcon.propTypes = {
    active: PropTypes.bool,
    order: PropTypes.string,
};

export const ColumnPropType = PropTypes.shape({
    key: PropTypes.string.isRequired,
    label: PropTypes.node.isRequired,
    render: PropTypes.func,
    numeric: PropTypes.bool,
    strong: PropTypes.bool,
    sortable: PropTypes.bool,
});

DataTable.propTypes = {
    columns: PropTypes.arrayOf(ColumnPropType).isRequired,
    rows: PropTypes.array.isRequired,
    rowKey: PropTypes.oneOfType([PropTypes.string, PropTypes.func]),
    loading: PropTypes.bool,
    sortField: PropTypes.string,
    sortOrder: PropTypes.string,
    onSort: PropTypes.func,
    pagination: PropTypes.shape({
        current: PropTypes.number,
        pageSize: PropTypes.number,
        total: PropTypes.number,
    }),
    onPageChange: PropTypes.func,
    emptyText: PropTypes.node,
    skeletonRows: PropTypes.number,
    renderExpanded: PropTypes.func,
    onExpand: PropTypes.func,
    onRowClick: PropTypes.func,
    isRowActive: PropTypes.func,
};
