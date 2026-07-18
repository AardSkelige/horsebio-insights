import { useState, useEffect, useCallback, useRef, useMemo } from 'react';

export function useAnalysisTable({ fetchFn, dataKey, defaultSort, defaultFilters }) {
    const [rows, setRows] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(false);
    const [filters, setFilters] = useState(defaultFilters);
    const [pagination, setPagination] = useState({ current: 1, pageSize: 10, total: 0 });
    const [sortField, setSortField] = useState(defaultSort);
    const [sortOrder, setSortOrder] = useState('desc');
    const [selectedItem, setSelectedItem] = useState(null);
    const [modalVisible, setModalVisible] = useState(false);
    const abortRef = useRef(null);
    const { current, pageSize } = pagination;

    const requestDeps = useMemo(() => ({
        ...filters,
        current,
        pageSize,
        sortField,
        sortOrder,
    }), [filters, current, pageSize, sortField, sortOrder]);

    const doFetch = useCallback(async () => {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        setLoading(true);

        const { current, pageSize, sortField: sf, sortOrder: so, ...filterVals } = requestDeps;
        const params = new URLSearchParams({
            page: String(current),
            pageSize: String(pageSize),
            sortField: sf,
            sortOrder: so,
        });
        Object.entries(filterVals).forEach(([k, v]) => {
            if (Array.isArray(v)) v.forEach(item => params.append(k, item));
            else if (v != null && v !== '') params.append(k, v);
        });

        try {
            const data = await fetchFn(params, abortRef.current.signal);
            if (data.status === 'success') {
                setRows(data.data[dataKey]);
                setStats(data.data.stats ?? null);
                setPagination(p => ({ ...p, total: data.data.total }));
            }
        } catch (e) {
            if (e.name !== 'AbortError') console.error(e);
        } finally {
            setLoading(false);
        }
    }, [requestDeps, fetchFn, dataKey]);

    useEffect(() => {
        doFetch();
        return () => abortRef.current?.abort();
    }, [doFetch]);

    const handleFiltersChange = (newFilters) => {
        setPagination(p => ({ ...p, current: 1 }));
        setFilters(newFilters);
    };

    const handleSort = (field) => {
        if (field === sortField) {
            setSortOrder(o => (o === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortField(field);
            setSortOrder('desc');
        }
        setPagination(p => ({ ...p, current: 1 }));
    };

    const handlePageChange = (page) => setPagination(p => ({ ...p, current: page }));
    const handleItemClick = (item) => { setSelectedItem(item); setModalVisible(true); };
    // selectedItem не обнуляем: модалка должна остаться смонтированной,
    // чтобы отыграть exit-анимацию закрытия
    const handleModalClose = () => setModalVisible(false);

    return {
        rows, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh: doFetch,
    };
}
