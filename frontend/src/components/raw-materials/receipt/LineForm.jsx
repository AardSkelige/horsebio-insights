import PropTypes from 'prop-types';
import { Check } from 'lucide-react';
import { Input } from '../../ui';
import { formatQuantity } from '../format';
import { sameAs, saved } from './draft';

export default function LineForm({ line, draft, onChange }) {
    const set = (field) => (e) => onChange({ ...draft, [field]: e.target.value });
    const unchanged = line.filled && sameAs(draft, saved(line));
    return (
        <div className="receipt__line">
            <div className="shelf__item-head">
                <span className="shelf__slot">{line.slot || '—'}</span>
                <span className="shelf__name">{line.name}</span>
                <span className="shelf__total">{formatQuantity(line.quantity, line.uom)}</span>
            </div>
            <div className="receipt__fields">
                <label className="receipt__field">
                    <span className="stock__label">Серия</span>
                    <Input block value={draft.series} onChange={set('series')} placeholder="с мешка" autoComplete="off" />
                </label>
                <label className="receipt__field">
                    <span className="stock__label">Годен до</span>
                    <Input block type="date" value={draft.expiry_date} onChange={set('expiry_date')} />
                </label>
                <label className="receipt__field receipt__field--wide">
                    <span className="stock__label">Производитель{!line.filled && line.manufacturer ? ' · из прошлой серии' : ''}</span>
                    <Input block value={draft.manufacturer} onChange={set('manufacturer')} placeholder="с мешка" autoComplete="off" />
                </label>
            </div>
            {unchanged && (
                <span className="receipt__done"><Check size={14} aria-hidden="true" /> Внесено</span>
            )}
        </div>
    );
}

LineForm.propTypes = {
    line: PropTypes.object.isRequired,
    draft: PropTypes.object.isRequired,
    onChange: PropTypes.func.isRequired,
};
