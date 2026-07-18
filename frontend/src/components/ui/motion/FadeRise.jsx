import PropTypes from 'prop-types';
import { m } from 'motion/react';

// inView: анимация срабатывает при попадании блока в вьюпорт (один раз),
// а не при монтировании — для секций ниже первого экрана
const FadeRise = ({ children, className, style, delay = 0, inView = false }) => (
    <m.div
        className={className}
        style={style}
        initial={{ opacity: 0, y: 12 }}
        {...(inView
            ? { whileInView: { opacity: 1, y: 0 }, viewport: { once: true, amount: 0.15 } }
            : { animate: { opacity: 1, y: 0 } })}
        transition={{ duration: 0.3, ease: 'easeOut', delay }}
    >
        {children}
    </m.div>
);

FadeRise.propTypes = {
    children: PropTypes.node.isRequired,
    className: PropTypes.string,
    style: PropTypes.object,
    delay: PropTypes.number,
    inView: PropTypes.bool,
};

export default FadeRise;
