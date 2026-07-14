// src/hooks/shipments/products/useProductFilters.js
import { useState, useMemo } from 'react';

export const useProductFilters = (initialData = []) => {
    const [filters, setFilters] = useState({
        searchTerm: '',
        startDate: null,
        endDate: null,
        selectedSubgroup: 'all'  // Добавляем фильтр по подгруппе
    });

    const filteredData = useMemo(() => {
        if (!initialData || !Array.isArray(initialData)) return [];

        return initialData.filter(item => {
            // Фильтр по подгруппе
            if (filters.selectedSubgroup !== 'all') {
                if (item.product_subgroup !== filters.selectedSubgroup) {
                    return false;
                }
            }

            // Фильтр по поиску
            if (filters.searchTerm) {
                const searchLower = filters.searchTerm.toLowerCase();
                const matchesSearch =
                    (item.product_name && item.product_name.toLowerCase().includes(searchLower)) ||
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
        }).map(item => ({
            ...item,
            price: parseFloat(item.price) || 0,
            total_sum: parseFloat(item.total_sum) || 0,
            quantity: parseFloat(item.quantity) || 0
        }));
    }, [initialData, filters]);

    return {
        filters,
        setFilters,
        filteredData
    };
};