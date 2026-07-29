import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';
import './Tooltip.css';

const Tooltip = ({
    content,
    children,
    placement = 'bottom',
    className = '',
    focusable = true,
}) => {
    const tooltipId = useId();
    const anchorRef = useRef(null);
    const [position, setPosition] = useState(null);

    const showTooltip = () => {
        const rect = anchorRef.current?.getBoundingClientRect();
        if (!rect) return;
        const tooltipWidth = Math.min(360, window.innerWidth * 0.7);
        const left = Math.max(12, Math.min(rect.left, window.innerWidth - tooltipWidth - 12));
        setPosition(placement === 'top'
            ? { left, bottom: window.innerHeight - rect.top + 7 }
            : { left, top: rect.bottom + 7 });
    };

    const hideTooltip = () => setPosition(null);

    useEffect(() => {
        if (!position) return undefined;
        window.addEventListener('resize', hideTooltip);
        window.addEventListener('scroll', hideTooltip, true);
        return () => {
            window.removeEventListener('resize', hideTooltip);
            window.removeEventListener('scroll', hideTooltip, true);
        };
    }, [position]);

    return (
        <span
            ref={anchorRef}
            className={`ui-tooltip ${className}`.trim()}
            tabIndex={focusable ? 0 : undefined}
            aria-describedby={tooltipId}
            onMouseEnter={showTooltip}
            onMouseLeave={hideTooltip}
            onFocus={showTooltip}
            onBlur={hideTooltip}
        >
            {children}
            {position && createPortal(
                <span
                    id={tooltipId}
                    role="tooltip"
                    className="ui-tooltip__bubble"
                    style={position}
                >
                    {content}
                </span>,
                document.body,
            )}
        </span>
    );
};

Tooltip.propTypes = {
    content: PropTypes.node.isRequired,
    children: PropTypes.node.isRequired,
    placement: PropTypes.oneOf(['top', 'bottom']),
    className: PropTypes.string,
    focusable: PropTypes.bool,
};

export default Tooltip;
