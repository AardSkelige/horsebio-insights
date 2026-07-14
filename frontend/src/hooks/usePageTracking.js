import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { getCookie } from '../utils/api';
import NAV_GROUPS from '../components/layout/sidebar/navGroups';

const PATH_NAMES = {};
NAV_GROUPS.forEach(group => {
    group.items.forEach(item => {
        // superuserOnly-страницы не трекаем: в аналитике нужна активность обычных пользователей
        if (group.superuserOnly || item.superuserOnly) return;
        PATH_NAMES[item.path] = item.label;
    });
});

const TICK_MS = 15000;    // шаг накопления активного времени
const MAX_GAP_MS = 60000; // разрыв больше минуты = сон/фриз устройства — не считаем

const sendTrack = (path, name, duration, keepalive = false) => {
    if (!path || !name || duration < 2) return;
    fetch('/api/auth/track/', {
        method: 'POST',
        credentials: 'include',
        keepalive,
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
        },
        body: JSON.stringify({ path, name, duration }),
    }).catch(() => {});
};

export function usePageTracking() {
    const location = useLocation();
    const activeMsRef = useRef(0);
    const lastTickRef = useRef(Date.now());
    const prevRef = useRef({ path: location.pathname, name: PATH_NAMES[location.pathname] });

    // Накопить время с прошлого тика. Пропуски (сон ноутбука, свёрнутый браузер)
    // отсекаются по MAX_GAP_MS — иначе они целиком попадали в duration.
    const collect = () => {
        const now = Date.now();
        const gap = now - lastTickRef.current;
        lastTickRef.current = now;
        if (!document.hidden && gap > 0 && gap < MAX_GAP_MS) {
            activeMsRef.current += gap;
        }
    };

    const flush = (keepalive = false) => {
        collect();
        const duration = Math.round(activeMsRef.current / 1000);
        activeMsRef.current = 0;
        const { path, name } = prevRef.current;
        sendTrack(path, name, duration, keepalive);
    };

    useEffect(() => {
        const timer = setInterval(collect, TICK_MS);

        const onVisibilityChange = () => {
            if (document.hidden) {
                // Tab hidden — send accumulated time and reset timer
                flush(true); // keepalive for reliability on close
            } else {
                // Tab visible again — start fresh (background time not counted)
                lastTickRef.current = Date.now();
            }
        };

        document.addEventListener('visibilitychange', onVisibilityChange);
        return () => {
            clearInterval(timer);
            document.removeEventListener('visibilitychange', onVisibilityChange);
        };
    }, []); // eslint-disable-line react-hooks/exhaustive-deps

    useEffect(() => {
        flush();
        lastTickRef.current = Date.now();
        prevRef.current = {
            path: location.pathname,
            name: PATH_NAMES[location.pathname],
        };
    }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
}
