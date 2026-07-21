import api from '../utils/api';

export const siteOrdersApi = {
    getList: (params, signal) => api.get('/site-orders/', { params, signal }),
    // Убирает заказ только из внутреннего журнала (state-файла); письмо и документы
    // в МойСклад не трогает — см. site_order_delete в backend/api/views/site_orders.py
    remove: (orderId) => api.delete(`/site-orders/${orderId}/`),
};
