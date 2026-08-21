import PropTypes from 'prop-types';
import AnimatedNumber from './motion/AnimatedNumber';

/**
 * Карточка показателя: подпись капслоком, крупное значение засечным,
 * при необходимости — сноска под ним.
 *
 * До появления общего примитива в приложении жило девять своих `StatCard`,
 * и они расходились во всём: размер значения 22 / 26 / 28, подпись весом
 * 500 или 600, трекинг 0.08 или 0.1, фон то карточный, то тёмный. Здесь всё
 * это сведено к одному набору с двумя тонами.
 *
 * Размер по умолчанию — 23px: компактная карточка читается в ряду из пяти
 * показателей и не спорит с заголовком страницы.
 *
 * - `tone="card"` — обычная карточка на светлой странице;
 * - `tone="dark"` — на тёмной подложке (сезонность, ключевые показатели);
 * - `icon` ставится перед подписью;
 * - `suffix` — единица измерения рядом со значением, набирается мельче;
 * - `note` — пояснение под значением;
 * - числовое `value` докручивается анимацией, строковое выводится как есть.
 */
export default function StatCard({
    title,
    value,
    size = 23,
    format,
    note,
    suffix,
    icon: Icon,
    tone = 'card',
    accent,
    className = '',
    ...rest
}) {
    return (
        <div className={['ui-stat', `ui-stat--${tone}`, className].filter(Boolean).join(' ')} {...rest}>
            <div className="ui-stat__title">
                {Icon && <Icon size={12} aria-hidden="true" />}
                {title}
            </div>

            <div className="ui-stat__value" style={{ fontSize: size, color: accent }}>
                {typeof value === 'number'
                    ? <AnimatedNumber value={value} format={format || String} />
                    : value}
                {suffix && <span className="ui-stat__suffix">{suffix}</span>}
            </div>

            {note && <div className="ui-stat__note">{note}</div>}
        </div>
    );
}

StatCard.propTypes = {
    title: PropTypes.node.isRequired,
    value: PropTypes.oneOfType([PropTypes.string, PropTypes.number, PropTypes.node]).isRequired,
    size: PropTypes.number,
    format: PropTypes.func,
    note: PropTypes.node,
    suffix: PropTypes.node,
    icon: PropTypes.elementType,
    tone: PropTypes.oneOf(['card', 'dark', 'plain']),
    accent: PropTypes.string,
    className: PropTypes.string,
};
