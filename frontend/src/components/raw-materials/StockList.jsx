import PropTypes from 'prop-types';
import { ChevronRight } from 'lucide-react';
import { EmptyState, Skeleton } from '../ui';
import { useIsMobile } from '../../hooks/useIsMobile';
import { plural } from '../../utils/formatters';
import Expiry from './Expiry';
import { formatQuantity, groupBySlot } from './format';

function SeriesTable({ item }) {
    const rows = item.batches.length ? item.batches : [{ id: 'none', series: '', expiry_date: null, quantity: item.quantity }];
    return (
        <table className="shelf__series">
            <thead>
                <tr>
                    <th>Серия</th>
                    <th>Годен до</th>
                    <th className="is-numeric">Есть</th>
                </tr>
            </thead>
            <tbody>
                {rows.map((batch) => (
                    <tr key={batch.id}>
                        <td>{batch.series ? <span className="stock__code">{batch.series}</span> : <span className="stock__none">—</span>}</td>
                        <td><Expiry date={batch.expiry_date} /></td>
                        <td className="is-numeric">{formatQuantity(batch.quantity, item.uom)}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

SeriesTable.propTypes = { item: PropTypes.object.isRequired };

function Material({ item, onOpen, showSlot = false }) {
    const open = () => onOpen(item);
    return (
        <div
            className="shelf__item"
            role="button"
            tabIndex={0}
            onClick={open}
            onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    open();
                }
            }}
        >
            <div className="shelf__item-head">
                {showSlot && <span className="shelf__slot">{item.slot || '—'}</span>}
                <span className="shelf__name">{item.name}</span>
                <span className="shelf__total">{formatQuantity(item.quantity, item.uom)}</span>
                <ChevronRight size={18} className="shelf__chevron" aria-hidden="true" />
            </div>
            <SeriesTable item={item} />
        </div>
    );
}

Material.propTypes = { item: PropTypes.object.isRequired, onOpen: PropTypes.func.isRequired, showSlot: PropTypes.bool };

export default function StockList({ items, loading, onOpen, emptyText, single = false }) {
    const isMobile = useIsMobile();
    if (loading) {
        return (
            <div className="shelf__items" aria-busy="true">
                {[...Array(4)].map((_, i) => <Skeleton key={i} height={130} style={{ borderRadius: 12 }} />)}
            </div>
        );
    }
    if (!items.length) return <EmptyState title={emptyText} />;

    const groups = single ? [{ slot: '', items }] : groupBySlot(items);
    if (!isMobile) {
        return (
            <div className="shelves is-flat">
                {groups.flatMap((group) => group.items).map((item) => (
                    <Material key={item.id} item={item} onOpen={onOpen} showSlot={!single} />
                ))}
            </div>
        );
    }
    return (
        <div className="shelves">
            {groups.map((group) => (
                <section key={group.slot || 'none'} className="shelf">
                    {!single && (
                        <header className="shelf__head">
                            <span className="shelf__slot">{group.slot || 'Без ячейки'}</span>
                            <span className="shelf__count">
                                {group.items.length} {plural(group.items.length, 'позиция', 'позиции', 'позиций')}
                            </span>
                        </header>
                    )}
                    <div className="shelf__items">
                        {group.items.map((item) => <Material key={item.id} item={item} onOpen={onOpen} />)}
                    </div>
                </section>
            ))}
        </div>
    );
}

StockList.propTypes = {
    items: PropTypes.array.isRequired,
    loading: PropTypes.bool,
    onOpen: PropTypes.func.isRequired,
    emptyText: PropTypes.string.isRequired,
    single: PropTypes.bool,
};
