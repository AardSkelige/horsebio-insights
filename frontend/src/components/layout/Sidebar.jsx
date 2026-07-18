import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import PropTypes from 'prop-types';
import { PanelLeftClose, PanelLeftOpen, X, RefreshCw } from 'lucide-react';
import { getFreshAuthStatus, clearAuthStatus, subscribeAuth } from '../../utils/authSession';
import { authApi } from '../../api/authApi';
import { useDataPanel } from '../../contexts/DataPanelContext';
import NavItem from './sidebar/NavItem';
import UtilBtn from './sidebar/UtilBtn';
import UserMenu from './sidebar/UserMenu';
import NAV_GROUPS from './sidebar/navGroups';
import {
    HOME_PREFERENCES_EVENT,
    MAX_PINNED_SECTIONS,
    publishHomePreferences,
} from '../../utils/homePreferences';

const W_OPEN = 240;
const W_CLOSED = 52;

export const Sidebar = ({ expanded, onToggle, isMobile, mobileOpen, onMobileClose, theme, onToggleTheme, dataPanelTriggerRef }) => {
    const location = useLocation();
    const navigate = useNavigate();
    const { toggle: toggleDataPanel } = useDataPanel();
    const [isSuperuser, setIsSuperuser] = useState(getFreshAuthStatus().isSuperuser === true);
    const [pinnedPaths, setPinnedPaths] = useState([]);
    // Ховер живёт на уровне сайдбара: одна layoutId-пилюля перетекает между пунктами
    const [hovPath, setHovPath] = useState(null);

    useEffect(() => subscribeAuth(s => setIsSuperuser(s.isSuperuser === true)), []);

    useEffect(() => {
        let active = true;
        authApi.home()
            .then((result) => { if (active) setPinnedPaths(result.data.pinnedPaths || []); })
            .catch(() => {});

        const handlePreferences = (event) => {
            if (Array.isArray(event.detail?.pinnedPaths)) setPinnedPaths(event.detail.pinnedPaths);
        };
        window.addEventListener(HOME_PREFERENCES_EVENT, handlePreferences);
        return () => {
            active = false;
            window.removeEventListener(HOME_PREFERENCES_EVENT, handlePreferences);
        };
    }, []);

    const isActive = (path) => location.pathname === path;
    const showExpanded = isMobile ? true : expanded;

    // На мобильном сначала закрываем шторку и только потом навигируем:
    // iOS снимает «снимок» страницы в момент смены history-записи, и открытый
    // сайдбар иначе попадает в снимок жеста «назад».
    const mobileNavigate = isMobile
        ? (path) => { onMobileClose(); setTimeout(() => navigate(path), 240); }
        : undefined;

    const handleLogout = async () => {
        try {
            await authApi.logout();
        } catch (e) {
            console.error(e);
        } finally {
            clearAuthStatus();
            sessionStorage.clear();
            navigate('/login', { replace: true });
        }
    };

    const handleTogglePin = async (path) => {
        const previous = pinnedPaths;
        const isPinned = previous.includes(path);
        if (!isPinned && previous.length >= MAX_PINNED_SECTIONS) return;

        const next = isPinned
            ? previous.filter((item) => item !== path)
            : [...previous, path];
        setPinnedPaths(next);
        publishHomePreferences(next);

        try {
            const result = await authApi.updateHome(next);
            setPinnedPaths(result.data.pinnedPaths);
            publishHomePreferences(result.data.pinnedPaths);
        } catch {
            setPinnedPaths(previous);
            publishHomePreferences(previous);
        }
    };

    const asideStyle = isMobile
        ? {
            position: 'fixed', top: 0, left: 0, height: '100%',
            width: W_OPEN, minWidth: W_OPEN,
            backgroundColor: 'var(--surface-dark)',
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden', flexShrink: 0,
            zIndex: 35,
            transform: `translateX(${mobileOpen ? 0 : -W_OPEN}px)`,
            transition: 'transform 220ms ease',
        }
        : {
            width: expanded ? W_OPEN : W_CLOSED,
            minWidth: expanded ? W_OPEN : W_CLOSED,
            height: '100vh',
            backgroundColor: 'var(--surface-dark)',
            display: 'flex', flexDirection: 'column',
            overflow: 'hidden', flexShrink: 0,
            transition: 'width 220ms ease, min-width 220ms ease',
            position: 'sticky', top: 0, zIndex: 30,
        };

    return (
        <aside style={asideStyle}>

            {/* Logo + toggle */}
            <div style={{
                height: isMobile ? 'calc(56px + env(safe-area-inset-top, 0px))' : 56,
                display: 'flex', alignItems: 'center',
                padding: showExpanded ? '0 10px 0 14px' : '0',
                paddingTop: isMobile ? 'env(safe-area-inset-top, 0px)' : 0,
                justifyContent: showExpanded ? 'space-between' : 'center',
                flexShrink: 0,
                borderBottom: '1px solid rgba(255,255,255,0.06)',
                transition: 'padding 220ms ease',
                boxSizing: 'border-box',
            }}>
                {showExpanded && (
                    <Link
                        to="/"
                        onClick={mobileNavigate ? (e) => { e.preventDefault(); mobileNavigate('/'); } : undefined}
                        style={{ display: 'flex', alignItems: 'center', gap: 8, textDecoration: 'none', flex: 1, overflow: 'hidden', minWidth: 0 }}
                    >
                        <span
                            className="app-logo-mark"
                            style={{ color: 'var(--primary)', '--logo-mark-width': '20px', '--logo-mark-height': '12px', flexShrink: 0 }}
                            aria-hidden="true"
                        />
                        <span style={{ fontFamily: 'var(--serif)', fontSize: '15px', color: 'var(--on-dark)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            HorseBio Insights
                        </span>
                    </Link>
                )}
                <button
                    onClick={isMobile ? onMobileClose : onToggle}
                    title={isMobile ? 'Закрыть' : showExpanded ? 'Свернуть' : 'Развернуть'}
                    style={{
                        width: 28, height: 28,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        borderRadius: 7, border: 'none',
                        background: 'transparent', color: 'var(--on-dark-soft)',
                        cursor: 'pointer', flexShrink: 0,
                        transition: 'background 150ms ease, color 150ms ease',
                    }}
                    onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.08)'; e.currentTarget.style.color = 'var(--on-dark)'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--on-dark-soft)'; }}
                >
                    {isMobile ? <X size={15} /> : showExpanded ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
                </button>
            </div>

            {/* Nav */}
            <nav
                className="sidebar-nav"
                style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden', padding: '6px 0', scrollbarWidth: 'none', WebkitOverflowScrolling: 'touch', overscrollBehavior: 'contain' }}
                onTouchStart={e => e.stopPropagation()}
                onTouchMove={e => e.stopPropagation()}
                onMouseLeave={() => setHovPath(null)}
            >
                {NAV_GROUPS.map((group, gi) => {
                    const items = group.items.filter(item => !item.superuserOnly || isSuperuser);
                    if (!items.length) return null;

                    return (
                        <div key={gi}>
                            {gi > 0 && !showExpanded && (
                                <div style={{ height: 1, margin: '6px 10px', backgroundColor: 'rgba(255,255,255,0.07)' }} />
                            )}
                            {group.label && (
                                <div style={{
                                    maxHeight: showExpanded ? '40px' : 0,
                                    opacity: showExpanded ? 1 : 0,
                                    overflow: 'hidden',
                                    transition: 'max-height 200ms ease, opacity 150ms ease',
                                }}>
                                    <div style={{
                                        padding: '10px 16px 4px',
                                        fontFamily: 'var(--sans)', fontSize: '10px',
                                        fontWeight: 600, letterSpacing: '0.08em',
                                        textTransform: 'uppercase', color: 'var(--muted-soft)',
                                    }}>
                                        {group.label}
                                    </div>
                                </div>
                            )}
                            {items.map(item => (
                                <NavItem
                                    key={item.path}
                                    path={item.path}
                                    label={item.label}
                                    icon={item.icon}
                                    expanded={showExpanded}
                                    active={isActive(item.path)}
                                    onNavigate={mobileNavigate}
                                    hovered={hovPath === item.path}
                                    onHover={setHovPath}
                                    pinned={pinnedPaths.includes(item.path)}
                                    pinDisabled={!pinnedPaths.includes(item.path) && pinnedPaths.length >= MAX_PINNED_SECTIONS}
                                    onTogglePin={item.path === '/' ? undefined : handleTogglePin}
                                />
                            ))}
                        </div>
                    );
                })}
            </nav>

            {/* Bottom utilities */}
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', padding: '8px 0', flexShrink: 0 }}>
                <UtilBtn
                    icon={RefreshCw}
                    label="Обновить данные"
                    expanded={showExpanded}
                    onClick={toggleDataPanel}
                    btnRef={dataPanelTriggerRef}
                />
                <UserMenu
                    expanded={showExpanded}
                    theme={theme}
                    onToggleTheme={onToggleTheme}
                    onLogout={handleLogout}
                    onProfile={() => (mobileNavigate ? mobileNavigate('/profile') : navigate('/profile'))}
                />
            </div>

            <style>{`
                .sidebar-nav::-webkit-scrollbar { display: none; }
                @keyframes sidebar-tooltip-in {
                    from { opacity: 0; transform: translateY(-50%) translateX(-4px); }
                    to   { opacity: 1; transform: translateY(-50%) translateX(0); }
                }
                @keyframes user-menu-in {
                    from { opacity: 0; transform: translateY(4px); }
                    to   { opacity: 1; transform: translateY(0); }
                }
            `}</style>
        </aside>
    );
};

Sidebar.propTypes = {
    expanded: PropTypes.bool.isRequired,
    onToggle: PropTypes.func.isRequired,
    isMobile: PropTypes.bool,
    mobileOpen: PropTypes.bool,
    onMobileClose: PropTypes.func,
    theme: PropTypes.string.isRequired,
    onToggleTheme: PropTypes.func.isRequired,
    dataPanelTriggerRef: PropTypes.object,
};

export default Sidebar;
