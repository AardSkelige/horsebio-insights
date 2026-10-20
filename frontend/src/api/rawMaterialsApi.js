import api from '../utils/api';

export const rawMaterialsApi = {
    list: (signal) => api.get('/raw-materials/', { signal }),
    refresh: () => api.post('/raw-materials/refresh/'),
};
