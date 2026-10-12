// src/api/materialsApi.js
import api from '../utils/api';

export const materialsApi = {
    getList: (params, signal) =>
        api.get('/materials/', { params, signal }),

    // Справочники для панели фильтров. Отдельный адрес, потому что списки
    // групп и поставщиков не стоят подсчёта расхода по всему справочнику.
    getFilters: (signal) =>
        api.get('/materials/filters/', { signal }),

    getDetails: (id, qs, signal) =>
        api.get(`/materials/${id}/`, { params: qs || undefined, signal }),
};
