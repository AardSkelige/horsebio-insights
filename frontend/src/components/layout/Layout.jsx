import { useLocation } from 'react-router-dom';
import PropTypes from 'prop-types';
import { X, Menu } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import FloatingLoadingCard from '../common/FloatingLoadingCard';
import DataManagementCard from '../home/components/DataManagementCard';
import { useDataPanel } from '../../contexts/DataPanelContext';
import Sidebar from './Sidebar';
import { usePageTracking } from '../../hooks/usePageTracking';

const MOBILE_BP = 768;

const Layout = ({ children }) => {
    const location = useLocation();
    const { open, close } = useDataPanel();
    const panelRef = useRef(null);
    const dataPanelTriggerRef = useRef(null);

    usePageTracking();

    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
    const [sidebarExpanded, setSidebarExpanded] = useState(
        () => localStorage.getItem('sidebar') !== 'collapsed'
    );
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < MOBILE_BP);
    const [mobileOpen, setMobileOpen] = useState(false);

    useEffect(() => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
    }, [theme]);

    useEffect(() => {
        const handler = (event) => {
            if (event.detail === 'light' || event.detail === 'dark') {
                setTheme(event.detail);
            }
        };
        window.addEventListener('app-theme-change', handler);
        return () => window.removeEventListener('app-theme-change', handler);
    }, []);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < MOBILE_BP);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    // Close mobile sidebar on navigation
    useEffect(() => { setMobileOpen(false); }, [location.pathname]);

    // Lock body scroll when mobile sidebar is open (prevents background scroll on iOS)
    useEffect(() => {
        if (!isMobile) return;
        if (mobileOpen) {
            document.body.style.overflow = 'hidden';
            document.body.style.touchAction = 'none';
        } else {
            document.body.style.overflow = '';
            document.body.style.touchAction = '';
        }
        return () => {
            document.body.style.overflow = '';
            document.body.style.touchAction = '';
        };
    }, [mobileOpen, isMobile]);

    // Swipe left to close sidebar. Opening is via the burger button only:
    // the left screen edge is reserved by the iOS back gesture, an edge-swipe
    // handler fires together with history navigation.
    useEffect(() => {
        if (!isMobile || !mobileOpen) return;
        const MIN_SWIPE_X = 60;
        let startX = null;
        let startY = null;
        let tracking = false;

        const onTouchStart = (e) => {
            const t = e.touches[0];
            startX = t.clientX;
            startY = t.clientY;
            tracking = true;
        };
        const onTouchMove = (e) => {
            if (!tracking) return;
            const t = e.touches[0];
            const dx = t.clientX - startX;
            const dy = Math.abs(t.clientY - startY);
            if (dy >= Math.abs(dx)) return; // vertical scroll — ignore
            if (dx < -MIN_SWIPE_X) {
                setMobileOpen(false);
                tracking = false;
            }
        };
        const onTouchEnd = () => { tracking = false; };

        document.addEventListener('touchstart', onTouchStart, { passive: true });
        document.addEventListener('touchmove', onTouchMove, { passive: true });
        document.addEventListener('touchend', onTouchEnd, { passive: true });
        return () => {
            document.removeEventListener('touchstart', onTouchStart);
            document.removeEventListener('touchmove', onTouchMove);
            document.removeEventListener('touchend', onTouchEnd);
        };
    }, [isMobile, mobileOpen]);

    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (dataPanelTriggerRef.current?.contains(e.target)) return;
            if (panelRef.current && !panelRef.current.contains(e.target)) close();
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open, close]);

    const toggleSidebar = () => setSidebarExpanded(v => {
        localStorage.setItem('sidebar', v ? 'collapsed' : 'expanded');
        return !v;
    });

    return (
        <div style={{ display: 'flex', height: '100vh', overflow: 'hidden', backgroundColor: 'var(--canvas)' }}>

            {/* Mobile backdrop */}
            {isMobile && (
                <div
                    onClick={() => setMobileOpen(false)}
                    onTouchMove={e => e.preventDefault()}
                    style={{
                        position: 'fixed', inset: 0, zIndex: 34,
                        backgroundColor: 'rgba(20,20,19,0.45)',
                        opacity: mobileOpen ? 1 : 0,
                        pointerEvents: mobileOpen ? 'auto' : 'none',
                        transition: 'opacity 220ms ease',
                        touchAction: 'none',
                    }}
                />
            )}

            <Sidebar
                expanded={sidebarExpanded}
                onToggle={toggleSidebar}
                isMobile={isMobile}
                mobileOpen={mobileOpen}
                onMobileClose={() => setMobileOpen(false)}
                theme={theme}
                onToggleTheme={() => setTheme(t => t === 'light' ? 'dark' : 'light')}
                dataPanelTriggerRef={dataPanelTriggerRef}
            />

            {/* Scrollable content area */}
            <div style={{ flex: 1, overflow: 'auto', minWidth: 0, display: 'flex', flexDirection: 'column' }}>

                {/* Mobile top bar */}
                {isMobile && (
                    <div style={{
                        position: 'sticky', top: 0, zIndex: 20,
                        height: 'calc(52px + env(safe-area-inset-top, 0px))',
                        backgroundColor: 'var(--canvas)',
                        borderBottom: '1px solid var(--hairline)',
                        display: 'flex', alignItems: 'center', gap: 12,
                        paddingTop: 'env(safe-area-inset-top, 0px)',
                        paddingLeft: 16, paddingRight: 16,
                        boxSizing: 'border-box',
                        flexShrink: 0,
                    }}>
                        <button
                            onClick={() => setMobileOpen(true)}
                            aria-label="Открыть меню"
                            style={{
                                width: 32, height: 32,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                borderRadius: 8, border: 'none',
                                background: 'transparent', color: 'var(--muted)',
                                cursor: 'pointer',
                            }}
                        >
                            <Menu size={18} />
                        </button>
                        <span
                            className="app-logo-mark"
                            style={{ color: 'var(--primary)', '--logo-mark-width': '20px', '--logo-mark-height': '12px' }}
                            aria-hidden="true"
                        />
                        <span style={{ fontFamily: 'var(--serif)', fontSize: '15px', color: 'var(--ink)' }}>
                            HorseBio Insights
                        </span>
                    </div>
                )}

                <main
                    key={location.pathname}
                    className="route-transition"
                    style={{ padding: '24px', flex: 1, boxSizing: 'border-box' }}
                >
                    {children}
                </main>
            </div>

            {/* Data panel backdrop */}
            <div style={{
                position: 'fixed', inset: 0, zIndex: 39,
                backgroundColor: 'rgba(20,20,19,0.25)',
                opacity: open ? 1 : 0,
                pointerEvents: open ? 'auto' : 'none',
                transition: 'opacity 200ms ease',
            }} />

            {/* Data panel */}
            <div ref={panelRef} style={{
                position: 'fixed', top: 0, left: 0, right: 0, zIndex: 40,
                backgroundColor: 'var(--canvas)',
                borderBottom: '1px solid var(--hairline)',
                boxShadow: '0 8px 32px rgba(20,20,19,0.10)',
                transform: open ? 'translateY(0)' : 'translateY(-8px)',
                opacity: open ? 1 : 0,
                pointerEvents: open ? 'auto' : 'none',
                transition: 'transform 200ms ease, opacity 200ms ease',
            }}>
                <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '20px 24px', position: 'relative' }}>
                    <button
                        onClick={close}
                        title="Закрыть"
                        style={{
                            position: 'absolute', top: '20px', right: '24px',
                            width: '28px', height: '28px',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            borderRadius: '8px', border: 'none',
                            background: 'transparent', color: 'var(--muted)',
                            cursor: 'pointer',
                        }}
                    >
                        <X size={15} />
                    </button>
                    <DataManagementCard />
                </div>
            </div>

            <FloatingLoadingCard />
        </div>
    );
};

Layout.propTypes = { children: PropTypes.node.isRequired };

export default Layout;
