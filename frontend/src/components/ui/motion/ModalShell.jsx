import PropTypes from 'prop-types';
import { createPortal } from 'react-dom';
import { AnimatePresence, m } from 'motion/react';
import { usePageLayer } from './usePageLayer';

// Общий каркас модалок: spring-всплытие панели, fade подложки,
// плавное закрытие через AnimatePresence. Компонент должен оставаться
// смонтированным при open=false, иначе exit-анимация не сыграет.
const ModalShell = ({ open, onClose, children, maxWidth = 1000 }) => {
    const layer = usePageLayer(open);
    const frame = layer
        ? { ...layer.panel, left: 0, right: 0, paddingTop: 40, paddingBottom: 40 + layer.extra }
        : { position: 'fixed', inset: 0, paddingTop: 40, paddingBottom: 40 };
    const visibleHeight = layer ? layer.panel.height - layer.extra : null;

    return createPortal(
    <AnimatePresence>
        {open && (
            <m.div
                key="scrim"
                data-modal-scrim
                onClick={onClose}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                style={{ ...(layer ? layer.scrim : { position: 'fixed', inset: 0 }), zIndex: 9990, background: 'var(--scrim)' }}
            />
        )}
        {open && (
            <div key="frame" style={{ ...frame, zIndex: 9999, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingLeft: 16, paddingRight: 16, pointerEvents: 'none' }}>
                <m.div
                    initial={{ opacity: 0, y: 24, scale: 0.96 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 12, scale: 0.98, transition: { duration: 0.15 } }}
                    transition={{ type: 'spring', stiffness: 350, damping: 30 }}
                    style={{ position: 'relative', background: 'var(--canvas)', borderRadius: 16, border: '1px solid var(--hairline)', width: '100%', maxWidth, maxHeight: visibleHeight ? visibleHeight - 80 : 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column', boxShadow: 'var(--shadow-menu)', pointerEvents: 'auto' }}
                >
                    {children}
                </m.div>
            </div>
        )}
    </AnimatePresence>,
    document.body,
    );
};

ModalShell.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    children: PropTypes.node,
    maxWidth: PropTypes.number,
};

export default ModalShell;
