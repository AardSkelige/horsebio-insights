import api from '../utils/api';

export const rawMaterialsApi = {
    list: (signal) => api.get('/raw-materials/', { signal }),
    refresh: () => api.post('/raw-materials/refresh/'),
    issues: (signal) => api.get('/raw-materials/issues/', { signal }),
    issue: (body) => api.post('/raw-materials/issues/', body),
    receipts: (signal) => api.get('/raw-materials/receipts/', { signal }),
    fillReceiptLine: (id, body) => api.post(`/raw-materials/receipts/lines/${id}/`, body),
};
