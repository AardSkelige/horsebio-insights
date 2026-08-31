import { useEffect } from 'react';
import PropTypes from 'prop-types';
import { createPortal } from 'react-dom';
import { AnimatePresence, m } from 'motion/react';

/**
 * Выдвижная панель справа: список или форма, которую человек разбирает,
 * не теряя страницу под ней. На телефоне занимает всю ширину.
 *
 * Движение — тканью, а не пружиной, в отличие от `ModalShell`. Пружина
 * с недокритическим затуханием проскакивает нулевую точку, и панель, доехав
 * до края, отходит назад — у полноэкранной шторки это видно как рывок и щель
 * справа. Модалке проскок идёт (она всплывает в центре), шторке — нет.
 *
 * Закрывается по Escape и по клику на подложку: то же поведение, что у модалки,
 * иначе панель приходится «искать, чем закрыть».
 */
const DrawerShell = ({ open, onClose, label, width = 400, children }) => {
    useEffect(() => {
        if (!open) return undefined;
        const onKeyDown = (event) => { if (event.key === 'Escape') onClose(); };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [open, onClose]);

    return createPortal(
        <AnimatePresence>
            {open && (
                <>
                    <m.div
                        className="ui-drawer__scrim"
                        onClick={onClose}
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.2, ease: 'easeOut' }}
                    />
                    <m.aside
                        className="ui-drawer"
                        role="dialog"
                        aria-modal="true"
                        aria-label={label}
                        style={{ width: `min(${width}px, 100vw)` }}
                        initial={{ x: '100%' }}
                        animate={{ x: 0 }}
                        exit={{ x: '100%', transition: { duration: 0.2, ease: 'easeIn' } }}
                        transition={{ duration: 0.3, ease: 'easeOut' }}
                    >
                        {children}
                    </m.aside>
                </>
            )}
        </AnimatePresence>,
        document.body,
    );
};

DrawerShell.propTypes = {
    open: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    label: PropTypes.string.isRequired,
    width: PropTypes.number,
    children: PropTypes.node,
};

export default DrawerShell;
