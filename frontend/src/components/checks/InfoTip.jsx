import { useState, useRef, useEffect, useLayoutEffect } from 'react';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';

const MARGIN = 8;

// Маленький «?» с подсказкой (единый стиль для страницы /checks).
// Пузырь рендерится порталом в body с position:fixed и зажимается в границы
// экрана: внутри страницы предки с transform (route-анимация, свайп-карточки)
// ломают fixed-позиционирование, а без зажима пузырь вылезает за край.
export default function InfoTip({ text, width = 270 }) {
    const [open, setOpen] = useState(false);
    const [pos, setPos] = useState(null);
    const triggerRef = useRef(null);
    const bubbleRef = useRef(null);

    useLayoutEffect(() => {
        if (!open) { setPos(null); return; }
        const r = triggerRef.current.getBoundingClientRect();
        const w = Math.min(width, window.innerWidth - MARGIN * 2);
        const left = Math.max(MARGIN, Math.min(r.left + r.width / 2 - w / 2, window.innerWidth - MARGIN - w));
        setPos({ top: r.bottom + MARGIN, left, width: w, visible: false });
    }, [open, width]);

    // Второй проход: зная высоту пузыря, переносим его над «?», если снизу не влезает
    useLayoutEffect(() => {
        if (!pos || pos.visible) return;
        const h = bubbleRef.current?.offsetHeight || 0;
        const r = triggerRef.current.getBoundingClientRect();
        const fitsBelow = r.bottom + MARGIN + h <= window.innerHeight - MARGIN;
        const top = !fitsBelow && r.top - MARGIN - h >= MARGIN ? r.top - MARGIN - h : r.bottom + MARGIN;
        setPos((p) => ({ ...p, top, visible: true }));
    }, [pos]);

    // Тап вне подсказки или скролл — закрыть (важно для iOS, где нет mouseleave)
    useEffect(() => {
        if (!open) return;
        const close = (e) => { if (!triggerRef.current?.contains(e.target)) setOpen(false); };
        const closeNow = () => setOpen(false);
        document.addEventListener('pointerdown', close);
        window.addEventListener('scroll', closeNow, true);
        window.addEventListener('resize', closeNow);
        return () => {
            document.removeEventListener('pointerdown', close);
            window.removeEventListener('scroll', closeNow, true);
            window.removeEventListener('resize', closeNow);
        };
    }, [open]);

    return (
        <span ref={triggerRef} style={{ position: 'relative', display: 'inline-flex', verticalAlign: 'middle' }}>
            <span
                onPointerEnter={(e) => { if (e.pointerType === 'mouse') setOpen(true); }}
                onPointerLeave={(e) => { if (e.pointerType === 'mouse') setOpen(false); }}
                onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
                style={{
                    width: 15, height: 15, borderRadius: '50%', border: '1px solid var(--muted-soft)',
                    color: 'var(--muted-soft)', fontSize: 10, fontFamily: 'var(--sans)', fontWeight: 600,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'help', userSelect: 'none',
                }}>?</span>
            {open && pos && createPortal(
                <span ref={bubbleRef} style={{
                    position: 'fixed', top: pos.top, left: pos.left, width: pos.width,
                    visibility: pos.visible ? 'visible' : 'hidden',
                    zIndex: 60, padding: '10px 12px', background: 'var(--surface-dark)', color: 'var(--on-dark)',
                    fontFamily: 'var(--sans)', fontSize: 12, lineHeight: 1.5, fontWeight: 400,
                    // сбрасываем наследование от заголовков (капс/разрядка)
                    textTransform: 'none', letterSpacing: 'normal',
                    borderRadius: 8, textAlign: 'left', whiteSpace: 'normal', boxSizing: 'border-box',
                    boxShadow: '0 6px 20px rgba(0,0,0,0.28)',
                }}>{text}</span>,
                document.body
            )}
        </span>
    );
}

InfoTip.propTypes = {
    text: PropTypes.node.isRequired,
    width: PropTypes.number,
};
