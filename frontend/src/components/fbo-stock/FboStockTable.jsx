import PropTypes from 'prop-types';
import { ChevronDown, ChevronUp, ChevronsUpDown } from 'lucide-react';
import { SkeletonRows } from '../ui/Skeleton';
import Tooltip from '../ui/Tooltip';

// Колонки названы так, как о них думает человек, который едет на склад, а не
// так, как они называются в МойСклад: «Остаток» и «Количество» рядом читаются
// как синонимы. Формула — подписью второй строкой в шапке. Ярко выделена одна
// колонка — «Можно взять», остальные приглушены: страница отвечает на один вопрос.
const COLUMNS = [
    { key: 'article', label: 'Артикул', width: 120 },
    { key: 'name', label: 'Название' },
    { key: 'stock', label: 'На складе', hint: 'физически лежит', num: true, width: 110 },
    { key: 'reserve', label: 'В резерве', hint: 'под заказы', num: true, width: 110 },
    { key: 'quantity', label: 'Можно взять', hint: 'склад − резерв', num: true, width: 130, accent: true },
    { key: 'in_transit', label: 'Ожидается', hint: 'план выпуска', num: true, width: 115 },
    { key: 'minimum_balance', label: 'Минимум', hint: 'не опускать ниже', num: true, width: 130 },
];

const MINIMUM_HINT = 'Неснижаемый остаток из карточки товара в МойСклад. Из «Количества» он не вычитается — это подсказка, что позиция уже кончается.';

const headerCell = {
    fontFamily: 'var(--sans)',
    fontSize: 11,
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.06em',
    color: 'var(--muted)',
    padding: '10px 12px',
    textAlign: 'left',
    whiteSpace: 'nowrap',
    cursor: 'pointer',
    userSelect: 'none',
    verticalAlign: 'bottom',
};

const hintStyle = {
    display: 'block',
    fontFamily: 'var(--mono)',
    fontSize: 10,
    fontWeight: 400,
    letterSpacing: 0,
    textTransform: 'none',
    color: 'var(--muted-soft)',
    marginTop: 3,
};

const bodyCell = {
    fontFamily: 'var(--sans)',
    fontSize: 13,
    color: 'var(--ink)',
    padding: '10px 12px',
    borderTop: '1px solid var(--hairline-soft)',
};

const numCell = { ...bodyCell, textAlign: 'right', fontVariantNumeric: 'tabular-nums lining-nums' };

const fmt = (value) => (value === 0 ? '—' : new Intl.NumberFormat('ru-RU').format(value));
const fmtTotal = (value) => new Intl.NumberFormat('ru-RU').format(value);

const plural = (count) => {
    const tail = count % 100;
    if (tail > 10 && tail < 20) return 'позиций';
    const last = count % 10;
    if (last === 1) return 'позиция';
    if (last >= 2 && last <= 4) return 'позиции';
    return 'позиций';
};

function SortIcon({ active, order }) {
    if (!active) return <ChevronsUpDown size={11} style={{ color: 'var(--muted-soft)', marginLeft: 3, flexShrink: 0 }} />;
    return order === 'asc'
        ? <ChevronUp size={11} style={{ color: 'var(--primary)', marginLeft: 3, flexShrink: 0 }} />
        : <ChevronDown size={11} style={{ color: 'var(--primary)', marginLeft: 3, flexShrink: 0 }} />;
}

SortIcon.propTypes = { active: PropTypes.bool, order: PropTypes.oneOf(['asc', 'desc']) };

function QuantityValue({ item }) {
    return (
        <span style={{
            fontWeight: 600,
            fontSize: 14,
            color: item.quantity < 0 ? 'var(--error)' : 'var(--ink)',
        }}>
            {item.quantity < 0 ? `−${fmtTotal(Math.abs(item.quantity))}` : fmt(item.quantity)}
        </span>
    );
}

QuantityValue.propTypes = { item: PropTypes.object.isRequired };

function MobileCards({ items }) {
    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map((item) => (
                <div key={item.code || item.article || item.name} style={{
                    background: 'var(--canvas)', border: '1px solid var(--hairline)',
                    borderRadius: 10, padding: '12px 14px',
                }}>
                    <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--muted)' }}>
                        {item.article || item.code}
                    </div>
                    <div style={{ fontFamily: 'var(--sans)', fontSize: 13.5, color: 'var(--ink)', margin: '3px 0 10px', lineHeight: 1.4 }}>
                        {item.name}
                    </div>
                    <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
                        <div>
                            <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                                Можно взять
                            </div>
                            <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--muted-soft)', margin: '1px 0 2px' }}>
                                {fmtTotal(item.stock)} − {fmtTotal(item.reserve)}
                            </div>
                            <QuantityValue item={item} />
                        </div>
                        <div>
                            <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                                Ожидается
                            </div>
                            <div style={{ fontSize: 14, marginTop: 15, fontVariantNumeric: 'tabular-nums' }}>
                                {fmt(item.in_transit)}
                            </div>
                        </div>
                        {item.below_minimum && (
                            <div>
                                <div style={{ fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                                    Минимум
                                </div>
                                <div style={{ fontSize: 14, marginTop: 15, color: 'var(--warning)', fontVariantNumeric: 'tabular-nums' }}>
                                    {fmtTotal(item.minimum_balance)}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

MobileCards.propTypes = { items: PropTypes.array.isRequired };

export default function FboStockTable({ items, loading, sort, onSortChange, isMobile }) {
    if (isMobile && !loading) return <MobileCards items={items} />;

    return (
        <div style={{
            background: 'var(--canvas)', border: '1px solid var(--hairline)',
            borderRadius: 10, overflowX: 'auto',
        }}>
            <table style={{ borderCollapse: 'collapse', width: '100%', minWidth: 820 }}>
                <thead>
                    <tr>
                        {COLUMNS.map((col) => (
                            <th
                                key={col.key}
                                onClick={() => onSortChange(col.key)}
                                style={{
                                    ...headerCell,
                                    width: col.width,
                                    textAlign: col.num ? 'right' : 'left',
                                    background: col.accent ? 'var(--surface-soft)' : undefined,
                                    color: col.accent ? 'var(--ink)' : 'var(--muted)',
                                }}
                            >
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: col.num ? 'flex-end' : 'flex-start' }}>
                                    {col.label}
                                    <SortIcon active={sort.key === col.key} order={sort.dir} />
                                </div>
                                {col.hint && <span style={hintStyle}>{col.hint}</span>}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {loading && <SkeletonRows cols={COLUMNS.length} rows={10} />}
                    {!loading && items.map((item) => (
                        <tr key={item.code || item.article || item.name}>
                            <td style={{ ...bodyCell, fontFamily: 'var(--mono)', fontSize: 11.5, color: 'var(--muted)', whiteSpace: 'nowrap' }}>
                                {item.article || item.code}
                            </td>
                            <td style={bodyCell}>{item.name}</td>
                            <td style={numCell}>{fmt(item.stock)}</td>
                            <td style={{ ...numCell, color: 'var(--muted-soft)' }}>{fmt(item.reserve)}</td>
                            <td style={{ ...numCell, background: 'var(--surface-soft)' }}><QuantityValue item={item} /></td>
                            <td style={{ ...numCell, color: 'var(--muted-soft)' }}>{fmt(item.in_transit)}</td>
                            <td style={{ ...numCell, color: item.below_minimum ? 'var(--warning)' : 'var(--muted-soft)' }}>
                                {item.below_minimum
                                    ? <Tooltip content={MINIMUM_HINT}>{fmtTotal(item.minimum_balance)}</Tooltip>
                                    : fmt(item.minimum_balance)}
                            </td>
                        </tr>
                    ))}
                </tbody>
                {!loading && items.length > 0 && (
                    <tfoot>
                        <tr>
                            {/* Складывать штуки разных товаров смысла нет — в подвале
                                только счётчик того, сколько строк сейчас в выборке */}
                            <td
                                colSpan={COLUMNS.length}
                                style={{
                                    ...bodyCell, borderTop: '1px solid var(--hairline)',
                                    background: 'var(--surface-soft)', color: 'var(--muted)', fontSize: 12.5,
                                }}
                            >
                                {items.length} {plural(items.length)}
                            </td>
                        </tr>
                    </tfoot>
                )}
            </table>
        </div>
    );
}

FboStockTable.propTypes = {
    items: PropTypes.array.isRequired,
    loading: PropTypes.bool,
    sort: PropTypes.shape({ key: PropTypes.string, dir: PropTypes.string }).isRequired,
    onSortChange: PropTypes.func.isRequired,
    isMobile: PropTypes.bool,
};
