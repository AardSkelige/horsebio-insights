import { useState, useMemo } from 'react';

export const useCounterpartyFilters = (initialData = []) => {
    const [filters, setFilters] = useState({
        searchTerm: '',
        startDate: null,
        endDate: null
    });

    const filteredData = useMemo(() => {
        if (!initialData || !Array.isArray(initialData)) return [];

        return initialData.filter(item => {
            // Фильтр по поиску
            if (filters.searchTerm) {
                const searchLower = filters.searchTerm.toLowerCase();
                const matchesSearch =
                    (item.counterparty_name && item.counterparty_name.toLowerCase().includes(searchLower)) ||
                    (item.shipment_number && item.shipment_number.toLowerCase().includes(searchLower));
                if (!matchesSearch) return false;
            }

            // Фильтр по датам
            if (filters.startDate) {
                const itemDate = new Date(item.shipment_date);
                const startDate = new Date(filters.startDate);
                if (itemDate < startDate) return false;
            }

            if (filters.endDate) {
                const itemDate = new Date(item.shipment_date);
                const endDate = new Date(filters.endDate);
                if (itemDate > endDate) return false;
            }

            return true;
        });
    }, [initialData, filters]);

    return {
        filters,
        setFilters,
        filteredData
    };
};

export default useCounterpartyFilters;