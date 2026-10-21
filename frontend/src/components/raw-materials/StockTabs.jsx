import { useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { useSectionNotifications } from '../../contexts/NotificationsContext';
import { useIsMobile } from '../../hooks/useIsMobile';
import './RawMaterialsPage.css';

const TABS = [
    { to: '/raw-materials', label: 'Остатки', end: true },
    { to: '/raw-materials/receipts', label: 'Приёмка', counted: true },
    { to: '/raw-materials/issues', label: 'Выдачи' },
    { to: '/raw-materials/qr', label: 'QR ячеек' },
];

const preload = () => Promise.all([
    import('./RawMaterialsPage'),
    import('./receipt/ReceiptsPage'),
    import('./issue/IssuesPage'),
    import('./issue/SlotLabels'),
]);

export default function StockTabs() {
    const isMobile = useIsMobile();
    const { items } = useSectionNotifications('raw-materials');

    useEffect(() => { if (!isMobile) preload(); }, [isMobile]);
    if (isMobile) return null;

    const waiting = items.filter((item) => item.key.startsWith('raw-materials:receipt:')).length;
    return (
        <nav className="stock-tabs" aria-label="Разделы склада сырья">
            {TABS.map((tab) => (
                <NavLink
                    key={tab.to}
                    to={tab.to}
                    end={tab.end}
                    className={({ isActive }) => `stock-tabs__tab${isActive ? ' is-active' : ''}`}
                >
                    {tab.label}
                    {tab.counted && waiting > 0 && <span className="stock-tabs__badge">{waiting}</span>}
                </NavLink>
            ))}
        </nav>
    );
}
