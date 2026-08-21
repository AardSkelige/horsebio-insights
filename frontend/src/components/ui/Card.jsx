import PropTypes from 'prop-types';

/**
 * Карточка-контейнер.
 *
 * `tone` задаёт поверхность: `card` — обычная, `quiet` — приглушённая для
 * вложенных блоков, `plain` — только рамка, без заливки.
 */
export default function Card({ title, tone = 'card', className = '', children, ...rest }) {
    const classes = [
        'ui-card',
        tone === 'quiet' ? 'ui-card--quiet' : '',
        tone === 'plain' ? 'ui-card--plain' : '',
        className,
    ].filter(Boolean).join(' ');

    return (
        <div className={classes} {...rest}>
            {title && <div className="ui-card__title">{title}</div>}
            {children}
        </div>
    );
}

Card.propTypes = {
    title: PropTypes.node,
    tone: PropTypes.oneOf(['card', 'quiet', 'plain']),
    className: PropTypes.string,
    children: PropTypes.node,
};
