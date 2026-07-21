import { useState, useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import { UserCircle, Sun, Moon, LogOut } from 'lucide-react';
import { useAuthStatus } from '../../../hooks/useAuthStatus';

const avatarBase = {
    width: 28, height: 28,
    borderRadius: '50%',
    backgroundColor: 'var(--primary)',
    color: 'var(--on-primary)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    fontFamily: 'var(--sans)',
    fontSize: '11px',
    fontWeight: 600,
    flexShrink: 0,
    userSelect: 'none',
};

const menuItemStyle = (hov, danger = false) => ({
    display: 'flex', alignItems: 'center', gap: 10,
    width: '100%', padding: '10px 16px',
    border: 'none',
    backgroundColor: hov ? 'rgba(255,255,255,0.06)' : 'transparent',
    color: danger && hov ? '#e57373' : 'var(--on-dark-soft)',
    cursor: 'pointer',
    transition: 'background 120ms ease, color 120ms ease',
    textAlign: 'left',
});

const UserMenu = ({ expanded, theme, onToggleTheme, onLogout, onProfile }) => {
    const [open, setOpen] = useState(false);
    const [menuPos, setMenuPos] = useState({ bottom: 0, left: 0, width: 0 });
    const [hov, setHov] = useState(false);
    const [themeHov, setThemeHov] = useState(false);
    const [hovItem, setHovItem] = useState(null);
    const auth = useAuthStatus();
    const btnRef = useRef(null);
    const menuRef = useRef(null);

    const firstName = auth.firstName || '';
    const lastName = auth.lastName || '';
    const username = auth.username || '';
    const email = auth.email || '';
    const isSuperuser = auth.isSuperuser === true;

    const initials = (firstName || lastName)
        ? ((firstName[0] || '') + (lastName[0] || '')).toUpperCase()
        : username.slice(0, 2).toUpperCase();

    const displayName = (firstName || lastName)
        ? [firstName, lastName].filter(Boolean).join(' ')
        : username;

    const handleOpen = () => {
        if (btnRef.current) {
            const r = btnRef.current.getBoundingClientRect();
            setMenuPos({ bottom: window.innerHeight - r.top + 8, left: r.left, width: Math.max(r.width, 200) });
        }
        setOpen(v => !v);
    };

    useEffect(() => {
        if (!open) return;
        const handler = (e) => {
            if (menuRef.current && !menuRef.current.contains(e.target) &&
                btnRef.current && !btnRef.current.contains(e.target)) {
                setOpen(false);
            }
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, [open]);

    return (
        <>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 4,
                margin: '1px 6px', width: 'calc(100% - 12px)', boxSizing: 'border-box',
            }}>
                <button
                    ref={btnRef}
                    onClick={handleOpen}
                    onMouseEnter={() => setHov(true)}
                    onMouseLeave={() => setHov(false)}
                    style={{
                        display: 'flex', alignItems: 'center',
                        justifyContent: expanded ? 'flex-start' : 'center',
                        gap: expanded ? 10 : 0,
                        padding: '7px 10px',
                        borderRadius: 8, border: 'none',
                        backgroundColor: hov || open ? 'rgba(255,255,255,0.06)' : 'transparent',
                        cursor: 'pointer',
                        transition: 'background 150ms ease',
                        overflow: 'hidden', whiteSpace: 'nowrap',
                        flex: 1, minWidth: 0,
                    }}
                >
                    <div style={avatarBase}>{initials}</div>
                    {expanded && (
                        <div style={{
                            display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
                            overflow: 'hidden',
                            opacity: expanded ? 1 : 0,
                            maxWidth: expanded ? '180px' : '0px',
                            transition: `opacity 120ms ease ${expanded ? '100ms' : '0ms'}, max-width 220ms ease`,
                        }}>
                            <span style={{
                                fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
                                color: 'var(--on-dark)', overflow: 'hidden',
                                textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '160px',
                            }}>{displayName}</span>
                            <span style={{
                                fontFamily: 'var(--sans)', fontSize: '11px',
                                color: 'var(--on-dark-soft)', whiteSpace: 'nowrap',
                            }}>{isSuperuser ? 'Суперпользователь' : 'Пользователь'}</span>
                        </div>
                    )}
                </button>

                {expanded && (
                    <button
                        onClick={(e) => { e.stopPropagation(); onToggleTheme(); }}
                        onMouseEnter={() => setThemeHov(true)}
                        onMouseLeave={() => setThemeHov(false)}
                        title={theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                        style={{
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            width: 30, height: 30, flexShrink: 0,
                            borderRadius: 8, border: 'none',
                            backgroundColor: themeHov ? 'rgba(255,255,255,0.06)' : 'transparent',
                            color: 'var(--on-dark-soft)',
                            cursor: 'pointer',
                            transition: 'background 150ms ease',
                        }}
                    >
                        {theme === 'dark'
                            ? <Sun size={15} />
                            : <Moon size={15} />
                        }
                    </button>
                )}
            </div>

            {open && (
                <div
                    ref={menuRef}
                    style={{
                        position: 'fixed',
                        bottom: menuPos.bottom, left: menuPos.left, minWidth: menuPos.width,
                        backgroundColor: 'var(--surface-dark-elevated)',
                        borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                        zIndex: 200, overflow: 'hidden',
                        animation: 'user-menu-in 150ms ease forwards',
                    }}
                >
                    <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <div style={{ ...avatarBase, width: 36, height: 36, fontSize: '13px' }}>{initials}</div>
                            <div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 600, color: 'var(--on-dark)' }}>
                                    {displayName}
                                </div>
                                <div style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--on-dark-soft)', marginTop: 1 }}>
                                    {email || username}
                                </div>
                            </div>
                        </div>
                    </div>

                    <button
                        onMouseEnter={() => setHovItem('profile')} onMouseLeave={() => setHovItem(null)}
                        onClick={() => { setOpen(false); onProfile(); }}
                        style={menuItemStyle(hovItem === 'profile')}
                    >
                        <UserCircle style={{ width: 15, height: 15, flexShrink: 0 }} />
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px' }}>Личный кабинет</span>
                    </button>

                    <button
                        onMouseEnter={() => setHovItem('theme')} onMouseLeave={() => setHovItem(null)}
                        onClick={() => { onToggleTheme(); setOpen(false); }}
                        style={menuItemStyle(hovItem === 'theme')}
                    >
                        {theme === 'dark'
                            ? <Sun style={{ width: 15, height: 15, flexShrink: 0 }} />
                            : <Moon style={{ width: 15, height: 15, flexShrink: 0 }} />
                        }
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px' }}>
                            {theme === 'dark' ? 'Светлая тема' : 'Тёмная тема'}
                        </span>
                    </button>

                    <div style={{ height: 1, margin: '2px 0', backgroundColor: 'rgba(255,255,255,0.07)' }} />

                    <button
                        onMouseEnter={() => setHovItem('logout')} onMouseLeave={() => setHovItem(null)}
                        onClick={() => { setOpen(false); onLogout(); }}
                        style={menuItemStyle(hovItem === 'logout', true)}
                    >
                        <LogOut style={{ width: 15, height: 15, flexShrink: 0 }} />
                        <span style={{ fontFamily: 'var(--sans)', fontSize: '13px' }}>Выйти</span>
                    </button>
                </div>
            )}
        </>
    );
};

UserMenu.propTypes = {
    expanded: PropTypes.bool.isRequired,
    theme: PropTypes.string.isRequired,
    onToggleTheme: PropTypes.func.isRequired,
    onLogout: PropTypes.func.isRequired,
    onProfile: PropTypes.func.isRequired,
};

export default UserMenu;
