import { useCallback, useEffect, useState } from 'react';
import { productionPlanApi } from '../../api/productionPlanApi';
import { downloadBlob } from '../../utils/api';

export default function useProductionPlan() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [error, setError] = useState(null);

    const reload = useCallback((signal) => {
        setError(null);
        return productionPlanApi.get(signal)
            .then(setData)
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить план'); });
    }, []);

    useEffect(() => {
        const controller = new AbortController();
        reload(controller.signal).finally(() => { if (!controller.signal.aborted) setLoading(false); });
        return () => controller.abort();
    }, [reload]);

    const refresh = useCallback(() => {
        setRefreshing(true);
        setError(null);
        productionPlanApi.refresh()
            .then(setData)
            .catch((err) => reload().then(() => setError(err.message || 'Не удалось обновить')))
            .finally(() => setRefreshing(false));
    }, [reload]);

    const exportExcel = useCallback(() => {
        setExporting(true);
        productionPlanApi.export()
            .then((blob) => downloadBlob(blob, `Производственный план ${new Date().toLocaleDateString('ru-RU')}.xlsx`))
            .catch(() => setError('Не удалось выгрузить Excel. Обновите страницу и попробуйте ещё раз'))
            .finally(() => setExporting(false));
    }, []);

    const toggleGreen = useCallback((row) => {
        productionPlanApi.setGreen(row.article, row.name, !row.green)
            .then(() => setData((prev) => ({
                ...prev,
                rows: prev.rows.map((r) => (r.article === row.article ? { ...r, green: !row.green } : r)),
            })))
            .catch((err) => setError(err.message));
    }, []);

    return { data, loading, refreshing, exporting, error, reload, refresh, exportExcel, toggleGreen };
}
