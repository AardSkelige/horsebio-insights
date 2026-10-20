import PropTypes from 'prop-types';
import { Trash2 } from 'lucide-react';
import { IconButton } from '../../ui';
import { formatQuantity } from '../format';

export default function IssueLine({ line, onRemove }) {
    return (
        <li className="issue-line">
            <div className="issue-line__main">
                <span className="issue-line__name">{line.name}</span>
                <span className="issue-line__meta">
                    {line.slot || 'Без ячейки'} · {line.series || 'без серии'}
                </span>
            </div>
            <span className="issue-line__qty">{formatQuantity(line.quantity, line.uom)}</span>
            {onRemove && <IconButton icon={Trash2} label={`Убрать ${line.name}`} onClick={onRemove} />}
        </li>
    );
}

IssueLine.propTypes = {
    line: PropTypes.object.isRequired,
    onRemove: PropTypes.func,
};
