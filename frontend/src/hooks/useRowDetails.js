import { useCallback, useState } from 'react';

/**
 * Подгрузка деталей строки таблицы по требованию, с кэшем.
 *
 * Кэш ключуется вместе с фильтрами: раскрытая строка показывает данные за
 * выбранный период, и при смене периода прежний ответ уже не годится.
 *
 *   const { load, get, isLoading } = useRowDetails({
 *       fetchFn: (id) => materialsApi.getDetails(id, qs),
 *       cacheKey: (id) => `${id}:${filters.startDate}:${filters.endDate}`,
 *   });
 *
 *   <DataTable onExpand={(row) => load(row.id)} renderExpanded={(row) => ...get(row.id)} />
 */
export function useRowDetails({ fetchFn, cacheKey }) {
    const [cache, setCache] = useState({});
    const [loadingKeys, setLoadingKeys] = useState({});

    const load = useCallback(async (id) => {
        const key = cacheKey(id);
        if (cache[key]) return cache[key];

        setLoadingKeys((prev) => ({ ...prev, [key]: true }));
        try {
            const data = await fetchFn(id);
            if (data?.status === 'success') {
                setCache((prev) => ({ ...prev, [key]: data.data }));
                return data.data;
            }
            return null;
        } catch {
            // Молча: раскрытая строка покажет «нет данных», а страница
            // продолжит работать — деталь не стоит блокирующей ошибки
            return null;
        } finally {
            setLoadingKeys((prev) => ({ ...prev, [key]: false }));
        }
    }, [cache, cacheKey, fetchFn]);

    const get = useCallback((id) => cache[cacheKey(id)], [cache, cacheKey]);
    const isLoading = useCallback((id) => Boolean(loadingKeys[cacheKey(id)]), [loadingKeys, cacheKey]);

    return { load, get, isLoading };
}
