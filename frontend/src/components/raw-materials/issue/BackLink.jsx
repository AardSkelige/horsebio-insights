import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';

export default function BackLink() {
    return (
        <Link to="/raw-materials" className="slot-page__back">
            <ArrowLeft size={14} aria-hidden="true" />
            Весь склад
        </Link>
    );
}
