import PropTypes from 'prop-types';
import { Badge } from '../ui';
import { formatDate } from '../../utils/formatters';
import { TARA_GROUP, expiryState, formatQuantity } from './format';

const EXPIRY_TONE = { expired: 'error', soon: 'warning', ok: 'neutral' };

function BatchLine({ batch, uom, showQuantity }) {
    const state = expiryState(batch.expiry_date);
    return (
        <li className="raw-materials__batch">
            <span className={batch.series ? 'raw-materials__series' : 'raw-materials__series raw-materials__series--none'}>
                {batch.series || 'Без серии'}
            </span>
            {state && (
                <Badge tone={EXPIRY_TONE[state]}>
                    {state === 'expired' ? 'Просрочена ' : 'до '}{formatDate(batch.expiry_date)}
                </Badge>
            )}
            {showQuantity && <span className="raw-materials__qty">{formatQuantity(batch.quantity, uom)}</span>}
        </li>
    );
}

BatchLine.propTypes = {
    batch: PropTypes.shape({
        series: PropTypes.string,
        expiry_date: PropTypes.string,
        quantity: PropTypes.number.isRequired,
    }).isRequired,
    uom: PropTypes.string,
    showQuantity: PropTypes.bool,
};

export default function MaterialRow({ item }) {
    const batches = item.group === TARA_GROUP ? item.batches.filter((b) => b.series) : item.batches;
    const showQuantity = batches.length > 1 || batches.some((b) => b.quantity !== item.quantity);
    return (
        <li className="raw-materials__item">
            <div className="raw-materials__head">
                <span className="raw-materials__name">{item.name}</span>
                <span className="raw-materials__total">{formatQuantity(item.quantity, item.uom)}</span>
            </div>
            {batches.length > 0 && (
                <ul className="raw-materials__batches">
                    {batches.map((batch) => (
                        <BatchLine key={batch.id} batch={batch} uom={item.uom} showQuantity={showQuantity} />
                    ))}
                </ul>
            )}
        </li>
    );
}

MaterialRow.propTypes = {
    item: PropTypes.shape({
        name: PropTypes.string.isRequired,
        group: PropTypes.string,
        uom: PropTypes.string,
        quantity: PropTypes.number.isRequired,
        batches: PropTypes.arrayOf(PropTypes.object).isRequired,
    }).isRequired,
};
