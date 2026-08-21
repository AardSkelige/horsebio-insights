import { useEffect, useState } from 'react';
import { MOBILE_BREAKPOINT } from '../theme/tokens';

/**
 * Мобильная раскладка активна.
 *
 * Заменяет дюжину копий одного и того же эффекта с `window.innerWidth` и
 * слушателем `resize`. Слушаем `matchMedia`, а не `resize`: он срабатывает
 * один раз на пересечении границы, а не на каждый пиксель перетаскивания.
 */
export function useIsMobile(breakpoint = MOBILE_BREAKPOINT) {
    const query = `(max-width: ${breakpoint - 1}px)`;

    const [isMobile, setIsMobile] = useState(
        () => typeof window !== 'undefined' && window.matchMedia(query).matches,
    );

    useEffect(() => {
        const mql = window.matchMedia(query);
        const handler = (e) => setIsMobile(e.matches);

        setIsMobile(mql.matches);
        mql.addEventListener('change', handler);
        return () => mql.removeEventListener('change', handler);
    }, [query]);

    return isMobile;
}
