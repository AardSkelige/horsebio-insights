import { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';
import { m } from 'motion/react';

const tooltipStyle = (top) => ({
    position: 'fixed',
    top,
    left: 60,
    y: '-50%',
    backgroundColor: 'var(--surface-dark-elevated)',
    color: 'var(--on-dark)',
    padding: '5px 10px',
    borderRadius: 6,
    fontFamily: 'var(--sans)',
    fontSize: '12px',
    fontWeight: 500,
    whiteSpace: 'nowrap',
    zIndex: 200,
    pointerEvents: 'none',
    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
});

const NavItem = ({ path, label, icon: Icon, expanded, active, onNavigate, hovered, onHover }) => {
    const [tipTop, setTipTop] = useState(0);
    const ref = useRef(null);

    const handleEnter = () => {
        if (ref.current) {
            const r = ref.current.getBoundingClientRect();
            setTipTop(r.top + r.height / 2);
        }
        onHover(path);
    };

    return (
        <>
            <Link
                ref={ref}
                to={path}
                onClick={onNavigate ? (e) => { e.preventDefault(); onNavigate(path); } : undefined}
                onMouseEnter={handleEnter}
                style={{
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: expanded ? 'flex-start' : 'center',
                    gap: expanded ? 10 : 0,
                    padding: '7px 10px',
                    margin: '1px 6px',
                    borderRadius: 8,
                    textDecoration: 'none',
                    whiteSpace: 'nowrap',
                }}
            >
                {/* Ховер-пилюля: одна на весь сайдбар, перетекает за курсором */}
                {hovered && (
                    <m.span
                        layoutId="sidebar-hover-pill"
                        transition={{ type: 'spring', stiffness: 550, damping: 45 }}
                        style={{ position: 'absolute', inset: 0, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.06)' }}
                    />
                )}
                {/* Активная пилюля: перелетает к выбранному пункту при навигации */}
                {active && (
                    <m.span
                        layoutId="sidebar-active-pill"
                        transition={{ type: 'spring', stiffness: 450, damping: 38 }}
                        style={{ position: 'absolute', inset: 0, borderRadius: 8, backgroundColor: 'rgba(255,255,255,0.10)' }}
                    />
                )}
                <Icon style={{
                    position: 'relative',
                    width: 16, height: 16, flexShrink: 0,
                    color: active ? 'var(--primary)' : 'var(--on-dark-soft)',
                    transition: 'color 150ms ease',
                }} />
                <span style={{
                    position: 'relative',
                    fontFamily: 'var(--sans)',
                    fontSize: '13px',
                    fontWeight: active ? 500 : 400,
                    color: active ? 'var(--on-dark)' : 'var(--on-dark-soft)',
                    opacity: expanded ? 1 : 0,
                    maxWidth: expanded ? '180px' : '0px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    transition: `opacity 120ms ease ${expanded ? '100ms' : '0ms'}, max-width 220ms ease`,
                }}>
                    {label}
                </span>
            </Link>
            {!expanded && hovered && (
                <m.div
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 28 }}
                    style={tooltipStyle(tipTop)}
                >
                    {label}
                </m.div>
            )}
        </>
    );
};

NavItem.propTypes = {
    path: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
    icon: PropTypes.elementType.isRequired,
    expanded: PropTypes.bool.isRequired,
    active: PropTypes.bool.isRequired,
    onNavigate: PropTypes.func,
    hovered: PropTypes.bool.isRequired,
    onHover: PropTypes.func.isRequired,
};

export default NavItem;
