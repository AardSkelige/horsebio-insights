import PropTypes from 'prop-types';
import { Info } from 'lucide-react';
import Tooltip from './Tooltip';

export default function Hint({ text }) {
    return (
        <Tooltip content={text} className="ui-hint">
            <Info size={12} aria-label={text} />
        </Tooltip>
    );
}

Hint.propTypes = {
    text: PropTypes.string.isRequired,
};
