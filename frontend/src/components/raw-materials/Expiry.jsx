import PropTypes from 'prop-types';
import { formatDate } from '../../utils/formatters';
import { expiryState } from './format';

export default function Expiry({ date, prefix = '' }) {
    if (!date) return <span className="stock__none">—</span>;
    const state = expiryState(date);
    return (
        <span className={`stock__expiry is-${state}`}>
            {state === 'expired' ? `просрочена ${formatDate(date)}` : `${prefix}${formatDate(date)}`}
        </span>
    );
}

Expiry.propTypes = { date: PropTypes.string, prefix: PropTypes.string };
