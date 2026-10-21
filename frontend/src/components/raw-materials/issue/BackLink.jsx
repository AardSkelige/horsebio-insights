import PropTypes from 'prop-types';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useIsMobile } from '../../../hooks/useIsMobile';
import '../RawMaterialsPage.css';

export default function BackLink({ mobileOnly = false }) {
    const isMobile = useIsMobile();
    if (mobileOnly && !isMobile) return null;
    return (
        <Link to="/raw-materials" className="slot-page__back">
            <ArrowLeft size={14} aria-hidden="true" />
            Весь склад
        </Link>
    );
}

BackLink.propTypes = { mobileOnly: PropTypes.bool };
