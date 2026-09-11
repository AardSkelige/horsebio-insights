// src/api/suppliesApi.js
import api from '../utils/api';

export const suppliesApi = {
    materials: {
        getList: (params, signal) =>
            api.get('/supplies/materials/list/', { params, signal }),

        // Справочник для панели фильтров: список групп не стоит пересчёта
        // поставок по всему справочнику материалов.
        getFilters: (signal) =>
            api.get('/supplies/materials/filters/', { signal }),

        getDetails: (id, qs, signal) =>
            api.get(`/supplies/materials/${id}/details/`, { params: qs || undefined, signal }),
    },

    suppliers: {
        getList: (params, signal) =>
            api.get('/supplies/suppliers/', { params, signal }),

        getDetails: (id, qs, signal) =>
            api.get(`/supplies/suppliers/${id}/details/`, { params: qs || undefined, signal }),
    },
};
