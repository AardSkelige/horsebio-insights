import api from '../utils/api';

export const productionPlanApi = {
    get: (signal) => api.get('/production-plan/', { signal }),
    refresh: () => api.post('/production-plan/refresh/'),
    export: () => api.get('/production-plan/export/', { responseType: 'blob' }),
    exclusions: (signal) => api.get('/production-plan/exclusions/', { signal }),
    addExclusion: (text) => api.post('/production-plan/exclusions/', { text }),
    removeExclusion: (id) => api.delete(`/production-plan/exclusions/${id}/`),
    setGreen: (article, name, green) => (green
        ? api.post('/production-plan/green/', { article, name })
        : api.delete('/production-plan/green/', { data: { article } })),
};
