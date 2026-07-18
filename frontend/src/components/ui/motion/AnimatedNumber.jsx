import PropTypes from 'prop-types';
import { useEffect, useRef } from 'react';
import { useReducedMotion, useSpring } from 'motion/react';

// Число «докручивается» до значения пружиной без ре-рендеров:
// spring пишет напрямую в textContent. При reduced motion — мгновенно.
const AnimatedNumber = ({ value, format = String }) => {
    const reduced = useReducedMotion();
    const ref = useRef(null);
    const spring = useSpring(reduced ? value : 0, { stiffness: 90, damping: 24 });

    useEffect(() => spring.on('change', (v) => {
        if (ref.current) ref.current.textContent = format(Math.round(v));
    }), [spring, format]);

    useEffect(() => {
        if (reduced) spring.jump(value);
        else spring.set(value);
    }, [value, reduced, spring]);

    return <span ref={ref}>{format(reduced ? value : 0)}</span>;
};

AnimatedNumber.propTypes = {
    value: PropTypes.number.isRequired,
    format: PropTypes.func,
};

export default AnimatedNumber;
