import PropTypes from 'prop-types';
import { LazyMotion, domMax, MotionConfig } from 'motion/react';

// Единая точка подключения motion: LazyMotion грузит фичи лениво
// (domMax — нужен для layout-анимаций «плывущих» табов и пилюль),
// strict запрещает полный motion.div (только лёгкий m.div),
// reducedMotion="user" отключает transform-анимации по системной настройке.
const MotionProvider = ({ children }) => (
    <LazyMotion features={domMax} strict>
        <MotionConfig reducedMotion="user">
            {children}
        </MotionConfig>
    </LazyMotion>
);

MotionProvider.propTypes = { children: PropTypes.node.isRequired };

export default MotionProvider;
