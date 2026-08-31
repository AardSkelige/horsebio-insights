/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import PropTypes from 'prop-types';
import { notificationsApi } from '../api/notificationsApi';
import { useAuthStatus } from '../hooks/useAuthStatus';

const NotificationsContext = createContext(null);

// Уведомления считаются по живым данным, но данные эти меняются не быстрее, чем
// человек успевает что-то сделать в МойСклад или на сайте. Пяти минут достаточно,
// а сервер к тому же держит свой кеш такой же длины.
const POLL_MS = 5 * 60 * 1000;

// При возврате на вкладку список стоит перечитать — но не чаще раза в минуту,
// иначе переключение между вкладками превращается в поток запросов.
const FOCUS_THROTTLE_MS = 60 * 1000;

const EMPTY = { items: [], counts: { total: 0, unseen: 0 }, by_source: {} };

export const NotificationsProvider = ({ children }) => {
    const auth = useAuthStatus();
    const authenticated = auth.isAuthenticated === true;

    const [data, setData] = useState(EMPTY);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [panelOpen, setPanelOpen] = useState(false);
    const loadedAtRef = useRef(0);
    const abortRef = useRef(null);

    const load = useCallback(async (refresh = false) => {
        abortRef.current?.abort();
        const controller = new AbortController();
        abortRef.current = controller;

        setLoading(true);
        try {
            const result = await notificationsApi.list(
                refresh ? { refresh: 1 } : undefined, controller.signal,
            );
            setData(result);
            setError(null);
            loadedAtRef.current = Date.now();
        } catch (e) {
            if (e.name === 'AbortError') return;
            // Молчаливая ошибка: колокольчик — не главная задача экрана, поэтому
            // он показывает её у себя внутри и не мешает работать со страницей
            setError(e?.message || 'Не удалось загрузить уведомления');
        } finally {
            if (!controller.signal.aborted) setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!authenticated) {
            setData(EMPTY);
            return undefined;
        }
        load();
        const timer = setInterval(() => load(), POLL_MS);
        return () => {
            clearInterval(timer);
            abortRef.current?.abort();
        };
    }, [authenticated, load]);

    useEffect(() => {
        if (!authenticated) return undefined;
        const handler = () => {
            if (document.visibilityState !== 'visible') return;
            if (Date.now() - loadedAtRef.current < FOCUS_THROTTLE_MS) return;
            load();
        };
        document.addEventListener('visibilitychange', handler);
        window.addEventListener('focus', handler);
        return () => {
            document.removeEventListener('visibilitychange', handler);
            window.removeEventListener('focus', handler);
        };
    }, [authenticated, load]);

    const setRead = useCallback(async (keys = [], read = true) => {
        // Сразу перерисовываем: ответ сервера придёт с тем же результатом, но
        // отметка должна ставиться под пальцем, а не через полсекунды
        setData((current) => {
            const touched = (item) => keys.length === 0 || keys.includes(item.key);
            const items = current.items.map(
                (item) => (touched(item) ? { ...item, seen: read } : item),
            );
            return {
                ...current,
                items,
                counts: { ...current.counts, unseen: items.filter((item) => !item.seen).length },
            };
        });
        try {
            setData(await notificationsApi.setRead(keys, read));
        } catch { /* отметка не критична: вернётся при следующем опросе */ }
    }, []);

    const openPanel = useCallback(() => setPanelOpen(true), []);
    const closePanel = useCallback(() => setPanelOpen(false), []);

    const value = useMemo(() => ({
        items: data.items || [],
        counts: data.counts || EMPTY.counts,
        bySource: data.by_source || {},
        loading,
        error,
        panelOpen,
        openPanel,
        closePanel,
        reload: load,
        setRead,
    }), [data, loading, error, panelOpen, openPanel, closePanel, load, setRead]);

    return (
        <NotificationsContext.Provider value={value}>
            {children}
        </NotificationsContext.Provider>
    );
};

NotificationsProvider.propTypes = { children: PropTypes.node.isRequired };

/**
 * Уведомления целиком: список, счётчики, состояние панели.
 *
 * Вне провайдера возвращает пустую заглушку — так компонент, вынутый в тест
 * или на страницу логина, не обязан знать про контекст.
 */
export const useNotifications = () => useContext(NotificationsContext) || {
    ...EMPTY,
    bySource: {},
    loading: false,
    error: null,
    panelOpen: false,
    openPanel: () => {},
    closePanel: () => {},
    reload: () => {},
    setRead: () => {},
};

/** Уведомления одного раздела — для встраивания в саму страницу раздела. */
export const useSectionNotifications = (source) => {
    const { items, loading } = useNotifications();
    const own = useMemo(() => items.filter((item) => item.source === source), [items, source]);
    return { items: own, loading };
};
