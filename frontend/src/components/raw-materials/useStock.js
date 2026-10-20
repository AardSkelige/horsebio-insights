import { useCallback, useEffect, useState } from 'react';
import { rawMaterialsApi } from '../../api/rawMaterialsApi';

export default function useStock() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [error, setError] = useState(null);

    const reload = useCallback((signal) => {
        setError(null);
        return rawMaterialsApi.list(signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить склад'); });
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        reload(controller.signal).finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [reload]);

    const refresh = useCallback(() => {
        setRefreshing(true);
        setError(null);
        rawMaterialsApi.refresh()
            .then(setData)
            .catch((err) => setError(err.message || 'Не удалось сверить с МойСклад'))
            .finally(() => setRefreshing(false));
    }, []);

    return { data, loading, refreshing, error, refresh, reload };
}
