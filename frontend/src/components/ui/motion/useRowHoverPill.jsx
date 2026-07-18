import { useRef, useState, useCallback } from 'react';
import { m } from 'motion/react';

// Ховер-подсветка строк таблицы, «перетекающая» за курсором (как в сайдбаре).
// Использование:
//   const { containerProps, rowHoverProps, pill } = useRowHoverPill();
//   <div {...containerProps}>{pill}<table>... <tr {...rowHoverProps}> ...</table></div>
// Контейнер получает position:relative; пилюля рисуется ПОД таблицей
// (она идёт раньше в DOM), поэтому фон строк должен оставаться прозрачным.
export function useRowHoverPill() {
    const containerRef = useRef(null);
    const [rect, setRect] = useState(null);
    const [visible, setVisible] = useState(false);

    const onRowEnter = useCallback((e) => {
        const cont = containerRef.current;
        if (!cont) return;
        const rowRect = e.currentTarget.getBoundingClientRect();
        const contRect = cont.getBoundingClientRect();
        setRect({ top: rowRect.top - contRect.top + cont.scrollTop, height: rowRect.height });
        setVisible(true);
    }, []);

    const onContainerLeave = useCallback(() => setVisible(false), []);

    const pill = rect ? (
        <m.div
            aria-hidden="true"
            initial={false}
            animate={{ top: rect.top, height: rect.height, opacity: visible ? 1 : 0 }}
            transition={{ type: 'spring', stiffness: 600, damping: 45 }}
            // z-index: -1 — под содержимым таблицы; isolation на контейнере
            // не даёт пилюле провалиться ниже фона страницы
            style={{ position: 'absolute', left: 0, right: 0, zIndex: -1, background: 'var(--surface-soft)', pointerEvents: 'none' }}
        />
    ) : null;

    return {
        containerProps: { ref: containerRef, onMouseLeave: onContainerLeave, style: { position: 'relative', isolation: 'isolate' } },
        rowHoverProps: { onMouseEnter: onRowEnter },
        pill,
    };
}
