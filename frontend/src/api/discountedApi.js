import api from '../utils/api';

export const discountedApi = {
    getList: (params, signal) => api.get('/discounted/', { params, signal }),
    // Снимает товар с продажи на сайте обменом CommerceML — см.
    // backend/api/services/site_exchange.py. В МойСклад ничего не меняет.
    delist: (productId) => api.post(`/discounted/${productId}/delist/`),
};
