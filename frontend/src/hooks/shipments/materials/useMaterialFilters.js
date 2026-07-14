// src/hooks/shipments/materials/useMaterialFilters.js
import { useState, useMemo } from 'react';

export const useMaterialFilters = (initialData = []) => {
    const [filters, setFilters] = useState({
        searchTerm: '',
        startDate: null,
        endDate: null,
        selectedGroup: 'all',
        selectedCounterparties: [] // Добавляем новый фильтр
    });

    const filteredData = useMemo(() => {
        if (!initialData || !Array.isArray(initialData)) return [];

        return initialData.reduce((result, item) => {
            // Фильтр по поиску
            if (filters.searchTerm) {
                const searchLower = filters.searchTerm.toLowerCase();
                const matchesSearch =
                    (item.raw_material__name && item.raw_material__name.toLowerCase().includes(searchLower)) ||
                    (item.raw_material__code && item.raw_material__code.toLowerCase().includes(searchLower));
                if (!matchesSearch) return result;
            }

            // Фильтр по группе
            if (filters.selectedGroup !== 'all') {
                if (item.raw_material__group !== filters.selectedGroup) {
                    return result;
                }
            }

            let filteredSuppliers = Array.isArray(item.suppliers) ? item.suppliers : [];

            // Фильтр по контрагентам
            if (filters.selectedCounterparties.length > 0) {
                filteredSuppliers = filteredSuppliers.filter(supplier =>
                    filters.selectedCounterparties.includes(supplier.name)
                );

                if (filteredSuppliers.length === 0) return result;
            }

            // Фильтр по датам
            if (filters.startDate || filters.endDate) {
                filteredSuppliers = filteredSuppliers.filter(supplier => {
                    const supplyDate = new Date(supplier.date);
                    return !(
                        (filters.startDate && supplyDate < new Date(filters.startDate)) ||
                        (filters.endDate && supplyDate > new Date(filters.endDate))
                    );
                });

                if (filteredSuppliers.length === 0) return result;
            }

            const totalQuantityFromSuppliers = filteredSuppliers.reduce((sum, supplier) =>
                sum + (parseFloat(supplier.quantity) || 0), 0);

            result.push({
                ...item,
                suppliers: filteredSuppliers,
                total_quantity: totalQuantityFromSuppliers
            });

            return result;
        }, []);
    }, [initialData, filters]);

    return {
        filters,
        setFilters,
        filteredData
    };
};

export default useMaterialFilters;
