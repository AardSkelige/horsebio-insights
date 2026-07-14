import { useState, useRef } from 'react';
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

const UtilBtn = ({ icon: Icon, label, expanded, onClick, btnRef }) => {
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
            <button
                ref={(el) => { ref.current = el; if (btnRef) btnRef.current = el; }}
                onClick={onClick}
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
                    border: 'none',
                    backgroundColor: hov ? 'rgba(255,255,255,0.06)' : 'transparent',
                    color: 'var(--on-dark-soft)',
                    cursor: 'pointer',
                    transition: 'background 150ms ease',
                    overflow: 'hidden',
                    whiteSpace: 'nowrap',
                    width: 'calc(100% - 12px)',
                    boxSizing: 'border-box',
                }}
            >
                <Icon style={{ width: 16, height: 16, flexShrink: 0 }} />
                <span style={{
                    fontFamily: 'var(--sans)',
                    fontSize: '13px',
                    opacity: expanded ? 1 : 0,
                    maxWidth: expanded ? '180px' : '0px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    transition: `opacity 120ms ease ${expanded ? '100ms' : '0ms'}, max-width 220ms ease`,
                }}>
                    {label}
                </span>
            </button>
            {!expanded && hov && <div style={tooltipStyle(tipTop)}>{label}</div>}
        </>
    );
};

UtilBtn.propTypes = {
    icon: PropTypes.elementType.isRequired,
    label: PropTypes.string.isRequired,
    expanded: PropTypes.bool.isRequired,
    onClick: PropTypes.func.isRequired,
    btnRef: PropTypes.object,
};

export default UtilBtn;
