import { useState, useEffect, useMemo } from 'react';
import { suppliesApi } from '../../../api/suppliesApi';

export const useSupplyData = () => {
    const [rawData, setRawData] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [filters, setFilters] = useState({
        searchTerm: '',
        startDate: null,
        endDate: null,
        group: 'all'
    });

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const result = await suppliesApi.getAll();
                if (result.status === 'success') {
                    setRawData(result.data);
                } else {
                    throw new Error(result.message || 'Failed to load data');
                }
            } catch (err) {
                console.error('Error fetching data:', err);
                setError(err.message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, []);

    const filteredData = useMemo(() => {
        let result = rawData;

        const safeIncludes = (text, searchTerm) => {
            if (!text) return false;
            return text.toString().toLowerCase().includes(searchTerm.toLowerCase());
        };

        if (filters.searchTerm) {
            const searchTerm = filters.searchTerm.trim();
            result = result.filter(item =>
                safeIncludes(item.supplier_name, searchTerm) ||
                safeIncludes(item.supply_number, searchTerm)
            );
        }

        if (filters.startDate) {
            const startDate = new Date(filters.startDate);
            startDate.setHours(0, 0, 0, 0);
            result = result.filter(item => new Date(item.supply_date) >= startDate);
        }

        if (filters.endDate) {
            const endDate = new Date(filters.endDate);
            endDate.setHours(23, 59, 59, 999);
            result = result.filter(item => new Date(item.supply_date) <= endDate);
        }

        if (filters.group && filters.group !== 'all') {
            result = result.filter(item =>
                item.items?.some(material => material.raw_material?.group === filters.group)
            );
        }

        return result;
    }, [rawData, filters]);

    return { data: filteredData, loading, error, filters, setFilters };
};

export default useSupplyData;
