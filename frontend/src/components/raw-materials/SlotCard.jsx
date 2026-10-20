import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { Card } from '../ui';
import MaterialRow from './MaterialRow';

export default function SlotCard({ slot, items }) {
    return (
        <Card className="raw-materials__slot">
            <h3 className="raw-materials__slot-head">
                {slot ? (
                    <Link to={`/raw-materials/slot/${encodeURIComponent(slot)}`} className="raw-materials__slot-link">
                        {slot}
                        <ChevronRight size={14} aria-hidden="true" />
                    </Link>
                ) : 'Без ячейки'}
            </h3>
            <ul className="raw-materials__items">
                {items.map((item) => <MaterialRow key={item.id} item={item} />)}
            </ul>
        </Card>
    );
}

SlotCard.propTypes = {
    slot: PropTypes.string.isRequired,
    items: PropTypes.arrayOf(PropTypes.object).isRequired,
};
