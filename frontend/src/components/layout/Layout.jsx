import { useLocation } from 'react-router-dom';
import PropTypes from 'prop-types';
import { m } from 'motion/react';
import { X, Menu } from 'lucide-react';
import { useState, useEffect, useRef } from 'react';
import FloatingLoadingCard from '../common/FloatingLoadingCard';
import DataManagementCard from '../home/components/DataManagementCard';
import { useDataPanel } from '../../contexts/DataPanelContext';
import { NotificationsProvider } from '../../contexts/NotificationsContext';
import { NotificationsBarButton, NotificationsPanel, PushSheet } from '../notifications';
import Sidebar from './Sidebar';
import { IconButton } from '../ui';
import { usePageTracking } from '../../hooks/usePageTracking';
import { useAuthStatus, useSuperuser } from '../../hooks/useAuthStatus';
import { navSection } from './sidebar/navGroups';
import { endIntro, introFor, introFull, switchTheme, ThemeIcon, useIntro, useLeaving } from '../ui/motion';
import { usePageLayer, usePageTint } from '../ui/motion/usePageLayer';
import { canSeePulse } from '../home/homeSections';

const MOBILE_BP = 768;

const Layout = ({ children }) => {
    const location = useLocation();
    const section = navSection(location.pathname);
    const entered = useRef(false);
    const introOnEnter = introFor(location.pathname, !entered.current);
    entered.current = true;
    const visited = useRef({ path: location.pathname, section, same: false, intro: introOnEnter });
    if (visited.current.path !== location.pathname) {
        visited.current = { path: location.pathname, section, same: visited.current.section === section, intro: introOnEnter };
    }
    const calmEnter = visited.current.same || visited.current.intro;
    const intro = useIntro();
    const leaving = useLeaving();
    const quickIntro = !canSeePulse(useAuthStatus());
    const { open, close } = useDataPanel();
    const panelRef = useRef(null);
    const dataPanelTriggerRef = useRef(null);
    const isSuperuser = useSuperuser();

    usePageTracking();

    const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light');
    const [sidebarExpanded, setSidebarExpanded] = useState(
        () => localStorage.getItem('sidebar') !== 'collapsed'
    );
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < MOBILE_BP);
    const [mobileOpen, setMobileOpen] = useState(false);
    const backdropLayer = usePageLayer(isMobile && mobileOpen);
    const tinted = usePageTint();

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

    useEffect(() => {
        if (!intro) return undefined;
        window.addEventListener('pointerdown', endIntro);
        window.addEventListener('keydown', endIntro);
        return () => {
            window.removeEventListener('pointerdown', endIntro);
            window.removeEventListener('keydown', endIntro);
        };
    }, [intro]);

    const toggleSidebar = () => setSidebarExpanded(v => {
        localStorage.setItem('sidebar', v ? 'collapsed' : 'expanded');
        return !v;
    });

    return (
        // Провайдер уведомлений здесь, а не в App: он нужен только на защищённых
        // страницах — и сайдбару со значками, и самим страницам разделов
        <NotificationsProvider>
        <div
            className={`app-shell${leaving ? ' app-outro' : intro ? ` app-intro${introFull() ? ' app-intro--full' : ''}${quickIntro ? ' app-intro--quick' : ''}` : ''}`}
        >
            {location.pathname === '/' && <div className="home-glow" aria-hidden="true" />}

            {/* Mobile backdrop */}
            {isMobile && (
                <div
                    onClick={() => setMobileOpen(false)}
                    onTouchMove={e => e.preventDefault()}
                    style={{
                        position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, ...backdropLayer?.scrim, zIndex: 34,
                        backgroundColor: 'var(--scrim)',
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
                onToggleTheme={(event) => switchTheme(theme === 'light' ? 'dark' : 'light', setTheme, event)}
                dataPanelTriggerRef={dataPanelTriggerRef}
            />

            {/* Scrollable content area */}
            <div className="app-content">

                {/* Mobile top bar */}
                {isMobile && (
                    <div className="intro-bar app-topbar" style={{
                        position: 'sticky', top: 0, zIndex: 20,
                        backgroundColor: tinted ? 'var(--scrim-solid)' : 'var(--canvas)',
                        borderBottom: '1px solid var(--hairline)',
                        display: 'flex', alignItems: 'center', gap: 12,
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
                        <span style={{ fontFamily: 'var(--display)', fontSize: '15px', color: 'var(--ink)' }}>
                            HorseBio Insights
                        </span>
                        <NotificationsBarButton />
                        <IconButton
                            className="app-topbar__btn"
                            label={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                            onClick={(event) => switchTheme(theme === 'light' ? 'dark' : 'light', setTheme, event)}
                        >
                            <ThemeIcon dark={theme === 'dark'} size={18} />
                        </IconButton>
                    </div>
                )}

                <main
                    key={location.pathname}
                    className={calmEnter ? undefined : 'route-transition'}
                    style={{ padding: '24px', flex: 1, boxSizing: 'border-box' }}
                >
                    {children}
                </main>
            </div>

            {/* Data panel backdrop */}
            <div style={{
                position: 'fixed', inset: 0, zIndex: open ? 9997 : 39,
                backgroundColor: 'var(--scrim-soft)',
                opacity: open ? 1 : 0,
                pointerEvents: open ? 'auto' : 'none',
                transition: 'opacity 200ms ease',
            }} />

            {/* Панель синхронизации — только суперпользователю: /parser/ закрыт
                правами с 10.09.2026, открывать её больше некому и незачем. */}
            {isSuperuser && (
            <m.div
                ref={panelRef}
                initial={false}
                animate={open ? { y: 0, opacity: 1 } : { y: -12, opacity: 0 }}
                transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                style={{
                    position: 'fixed', top: 0, left: 0, right: 0, zIndex: open ? 9998 : 40,
                    backgroundColor: 'var(--canvas)',
                    borderBottom: '1px solid var(--hairline)',
                    boxShadow: 'var(--shadow-soft)',
                    pointerEvents: open ? 'auto' : 'none',
                    // Панель выезжает от самого верха экрана, поэтому на телефоне
                    // её шапка уходила под статус-бар, а длинное содержимое —
                    // за нижний край без возможности доскроллить
                    paddingTop: 'var(--app-head-top)',
                    maxHeight: '100dvh',
                    overflowY: 'auto',
                    overscrollBehavior: 'contain',
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
            </m.div>
            )}

            <FloatingLoadingCard />
            <NotificationsPanel />
            <PushSheet quiet={intro || leaving || mobileOpen} />
        </div>
        </NotificationsProvider>
    );
};

Layout.propTypes = { children: PropTypes.node.isRequired };

export default Layout;
