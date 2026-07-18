import PropTypes from 'prop-types';
import { createPortal } from 'react-dom';
import { AnimatePresence, m } from 'motion/react';

// Общий каркас модалок: spring-всплытие панели, fade подложки,
// плавное закрытие через AnimatePresence. Компонент должен оставаться
// смонтированным при open=false, иначе exit-анимация не сыграет.
const ModalShell = ({ open, onClose, children, maxWidth = 1000 }) => createPortal(
    <AnimatePresence>
        {open && (
            <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '40px 16px' }}>
                <m.div
                    onClick={onClose}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    style={{ position: 'absolute', inset: 0, background: 'rgba(20,20,19,0.55)' }}
                />
                <m.div
                    initial={{ opacity: 0, y: 24, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 12, scale: 0.98, transition: { duration: 0.15 } }}
                    transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                    style={{ position: 'relative', background: 'var(--canvas)', borderRadius: 16, border: '1px solid var(--hairline)', width: '100%', maxWidth, maxHeight: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column', boxShadow: '0 8px 40px rgba(20,20,19,0.18)' }}
                >
                    {children}
                </m.div>
            </div>
        )}
    </AnimatePresence>,
    document.body
);

ModalShell.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    children: PropTypes.node,
    maxWidth: PropTypes.number,
};

export default ModalShell;
