import { useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import PropTypes from 'prop-types';

const tooltipStyle = (top) => ({
    position: 'fixed',
    top,
    left: 60,
    transform: 'translateY(-50%)',
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
    animation: 'sidebar-tooltip-in 150ms ease forwards',
});

const NavItem = ({ path, label, icon: Icon, expanded, active, onNavigate }) => {
    const [hov, setHov] = useState(false);
    const [tipTop, setTipTop] = useState(0);
    const ref = useRef(null);

    const handleEnter = () => {
        setHov(true);
        if (ref.current) {
            const r = ref.current.getBoundingClientRect();
            setTipTop(r.top + r.height / 2);
        }
    };

    return (
        <>
            <Link
                ref={ref}
                to={path}
                onClick={onNavigate ? (e) => { e.preventDefault(); onNavigate(path); } : undefined}
                onMouseEnter={handleEnter}
                onMouseLeave={() => setHov(false)}
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: expanded ? 'flex-start' : 'center',
                    gap: expanded ? 10 : 0,
                    padding: '7px 10px',
                    margin: '1px 6px',
                    borderRadius: 8,
                    textDecoration: 'none',
                    backgroundColor: active
                        ? 'rgba(255,255,255,0.10)'
                        : hov ? 'rgba(255,255,255,0.06)' : 'transparent',
                    transition: 'background 150ms ease',
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                }}
            >
                <Icon style={{
                    width: 16, height: 16, flexShrink: 0,
                    color: active ? 'var(--primary)' : 'var(--on-dark-soft)',
                    transition: 'color 150ms ease',
                }} />
                <span style={{
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
            {!expanded && hov && <div style={tooltipStyle(tipTop)}>{label}</div>}
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
};

export default NavItem;
