import { useCallback, useEffect, useState } from 'react';
import { rawMaterialsApi } from '../../api/rawMaterialsApi';
import { useNotifications } from '../../contexts/NotificationsContext';
import { getFreshAuthStatus } from '../../utils/authSession';

let remembered = { user: null, data: null };

const rememberedForMe = () => (remembered.user === getFreshAuthStatus().username ? remembered.data : null);

export default function useStock() {
    const [data, setStoredData] = useState(rememberedForMe);
    const [loading, setLoading] = useState(() => !rememberedForMe());
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState(null);

    const setData = useCallback((fresh) => {
        remembered = { user: getFreshAuthStatus().username, data: fresh };
        setStoredData(fresh);
    }, []);

    const reload = useCallback((signal) => {
        setError(null);
        return rawMaterialsApi.list(signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить склад'); });
    }, [setData]);

    useEffect(() => {
        const controller = new AbortController();
        reload(controller.signal).finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [reload]);

    const { reload: reloadNotifications } = useNotifications();

    const refresh = useCallback(() => {
        setRefreshing(true);
        setError(null);
        rawMaterialsApi.refresh()
            .then((fresh) => {
                setData(fresh);
                reloadNotifications();
            })
            .catch((err) => setError(err.message || 'Не удалось сверить с МойСклад'))
            .finally(() => setRefreshing(false));
    }, [reloadNotifications, setData]);

    return { data, loading, refreshing, error, refresh, reload };
}
