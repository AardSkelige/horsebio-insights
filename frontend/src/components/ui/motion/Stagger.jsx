import PropTypes from 'prop-types';
import { m } from 'motion/react';

// Почерк движения: 300ms ease-out, подъём 12px, каскад 50ms.
const containerVariants = (delay) => ({
    hidden: {},
    show: { transition: { staggerChildren: 0.05, delayChildren: delay } },
});

const itemVariants = {
    hidden: { opacity: 0, y: 12 },
    show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } },
};

export const Stagger = ({ children, className, style, delay = 0 }) => (
    <m.div
        className={className}
        style={style}
        initial="hidden"
        animate="show"
        variants={containerVariants(delay)}
    >
        {children}
    </m.div>
);

Stagger.propTypes = {
    children: PropTypes.node.isRequired,
    className: PropTypes.string,
    style: PropTypes.object,
    delay: PropTypes.number,
};

export const StaggerItem = ({ children, className, style }) => (
    <m.div className={className} style={style} variants={itemVariants}>
        {children}
    </m.div>
);

StaggerItem.propTypes = {
    children: PropTypes.node.isRequired,
    className: PropTypes.string,
    style: PropTypes.object,
};
