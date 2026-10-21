import { useCallback, useEffect, useState } from 'react';
import { rawMaterialsApi } from '../../../api/rawMaterialsApi';

export default function useReceipts() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);

    const load = useCallback((signal) => {
        setError(null);
        return rawMaterialsApi.receipts(signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить приёмки'); });
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        load(controller.signal);
        return () => controller.abort();
    }, [load]);

    return { data, setData, error, reload: load };
}
