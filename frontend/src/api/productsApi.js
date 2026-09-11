// src/api/productsApi.js
import api from '../utils/api';

export const productsApi = {
    getList: (params, signal) =>
        api.get('/products/', { params, signal }),

    // Справочники для панели фильтров. Отдельный адрес, потому что списки
    // подгрупп и каналов не стоят полной агрегации по отгрузкам.
    getFilters: (signal) =>
        api.get('/products/filters/', { signal }),

    getDetails: (id, qs, signal) =>
        api.get(`/products/${id}/`, { params: qs || undefined, signal }),
};
