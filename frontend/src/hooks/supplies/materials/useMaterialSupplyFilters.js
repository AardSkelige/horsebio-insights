import { useState, useMemo } from 'react';

export const useMaterialSupplyFilters = (initialData = []) => {
    const [filters, setFilters] = useState({
        searchTerm: '',
        startDate: null,
        endDate: null,
        selectedGroup: 'all'
    });

    const filteredData = useMemo(() => {
        if (!initialData || !Array.isArray(initialData)) return [];

        return initialData.filter(item => {
            // Фильтр по поиску
            if (filters.searchTerm) {
                const searchLower = filters.searchTerm.toLowerCase();
                const matchesSearch =
                    (item.raw_material__name && item.raw_material__name.toLowerCase().includes(searchLower)) ||
                    (item.raw_material__code && item.raw_material__code.toLowerCase().includes(searchLower));
                if (!matchesSearch) return false;
            }

            // Фильтр по группе
            if (filters.selectedGroup !== 'all') {
                if (item.raw_material__group !== filters.selectedGroup) {
                    return false;
                }
            }

            // Фильтр по датам
            if (filters.startDate) {
                const startDate = new Date(filters.startDate);
                const supplyDates = item.supplies ? item.supplies.map(s => new Date(s.date)) : [];
                const hasSuppliesAfterStart = supplyDates.some(date => date >= startDate);
                if (!hasSuppliesAfterStart) return false;
            }

            if (filters.endDate) {
                const endDate = new Date(filters.endDate);
                const supplyDates = item.supplies ? item.supplies.map(s => new Date(s.date)) : [];
                const hasSuppliesBeforeEnd = supplyDates.some(date => date <= endDate);
                if (!hasSuppliesBeforeEnd) return false;
            }

            return true;
        }).map(item => {
            // Если есть фильтры по датам, фильтруем также supplies
            if ((filters.startDate || filters.endDate) && item.supplies) {
                const startDate = filters.startDate ? new Date(filters.startDate) : null;
                const endDate = filters.endDate ? new Date(filters.endDate) : null;

                const filteredSupplies = item.supplies.filter(supply => {
                    const supplyDate = new Date(supply.date);
                    if (startDate && supplyDate < startDate) return false;
                    if (endDate && supplyDate > endDate) return false;
                    return true;
                });

                return {
                    ...item,
                    supplies: filteredSupplies,
                    // Пересчитываем итоговые показатели на основе отфильтрованных приемок
                    total_quantity: filteredSupplies.reduce(
                        (sum, supply) => sum + (parseFloat(supply.quantity) || 0),
                        0
                    ),
                    total_sum: filteredSupplies.reduce(
                        (sum, supply) => sum + (parseFloat(supply.total) || 0),
                        0
                    ),
                    avg_price: filteredSupplies.length > 0
                        ? filteredSupplies.reduce((sum, supply) => sum + (parseFloat(supply.price) || 0), 0) / filteredSupplies.length
                        : 0
                };
            }

            return item;
        });
    }, [initialData, filters]);

    return {
        filters,
        setFilters,
        filteredData
    };
};

export default useMaterialSupplyFilters;