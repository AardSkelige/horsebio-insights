import { useCallback, useState } from 'react';
import PropTypes from 'prop-types';
import { useNavigate } from 'react-router-dom';
import { ScanLine } from 'lucide-react';
import { Button } from '../../ui';
import Scanner from './Scanner';
import './issue.css';

export default function ScanButton({ slots, variant = 'primary', block = false }) {
    const [open, setOpen] = useState(false);
    const navigate = useNavigate();

    const close = useCallback(() => setOpen(false), []);
    const found = useCallback((slot) => {
        setOpen(false);
        navigate(`/raw-materials/slot/${encodeURIComponent(slot)}`);
    }, [navigate]);

    return (
        <>
            <Button variant={variant} block={block} icon={ScanLine} onClick={() => setOpen(true)}>Сканировать</Button>
            <Scanner open={open} onClose={close} onFound={found} slots={slots} />
        </>
    );
}

ScanButton.propTypes = {
    slots: PropTypes.arrayOf(PropTypes.string).isRequired,
    variant: PropTypes.oneOf(['primary', 'soft']),
    block: PropTypes.bool,
};
