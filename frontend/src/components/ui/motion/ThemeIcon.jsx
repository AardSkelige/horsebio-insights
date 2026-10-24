import PropTypes from 'prop-types';
import { AnimatePresence, m } from 'motion/react';
import { Moon, Sun } from 'lucide-react';

const ThemeIcon = ({ dark, size }) => (
    <span style={{ position: 'relative', display: 'inline-flex', width: size, height: size, flexShrink: 0 }}>
        <AnimatePresence initial={false}>
            <m.span
                key={dark ? 'sun' : 'moon'}
                initial={{ opacity: 0, rotate: -90, scale: 0.5 }}
                animate={{ opacity: 1, rotate: 0, scale: 1 }}
                exit={{ opacity: 0, rotate: 90, scale: 0.5 }}
                transition={{ duration: 0.4, ease: [0.65, 0, 0.35, 1] }}
                style={{ position: 'absolute', inset: 0, display: 'flex' }}
            >
                {dark ? <Sun size={size} /> : <Moon size={size} />}
            </m.span>
        </AnimatePresence>
    </span>
);

ThemeIcon.propTypes = {
    dark: PropTypes.bool.isRequired,
    size: PropTypes.number.isRequired,
};

export default ThemeIcon;
