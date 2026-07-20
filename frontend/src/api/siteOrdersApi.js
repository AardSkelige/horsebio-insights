import api from '../utils/api';

export const siteOrdersApi = {
    getList: (params, signal) => api.get('/site-orders/', { params, signal }),
};
