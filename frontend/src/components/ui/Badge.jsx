import PropTypes from 'prop-types';

/**
 * Плашка статуса.
 *
 * Тон берётся из семантических токенов, поэтому текст остаётся читаемым
 * в обеих темах. Раньше такие плашки собирались вручную из тройки
 * `{ color: тёмный хекс, bg: rgba(…, 0.1), border: rgba(…, 0.3) }`,
 * и на тёмном фоне текст в них пропадал.
 */
export default function Badge({ tone = 'neutral', icon: Icon, className = '', children, ...rest }) {
    const classes = ['ui-badge', `ui-badge--${tone}`, className].filter(Boolean).join(' ');
    return (
        <span className={classes} {...rest}>
            {Icon && <Icon size={11} aria-hidden="true" />}
            {children}
        </span>
    );
}

Badge.propTypes = {
    tone: PropTypes.oneOf(['neutral', 'success', 'warning', 'error', 'info', 'accent']),
    icon: PropTypes.elementType,
    className: PropTypes.string,
    children: PropTypes.node,
};
