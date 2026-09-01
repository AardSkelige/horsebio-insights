import api from '../utils/api';

export const siteOrdersApi = {
    getList: (params, signal) => api.get('/site-orders/', { params, signal }),
    // Убирает заказ только из внутреннего журнала (state-файла); письмо и документы
    // в МойСклад не трогает — см. site_order_delete в backend/api/views/site_orders.py
    remove: (orderId) => api.delete(`/site-orders/${orderId}/`),
    // Отмена доставки Ozon. У Ozon она асинхронная: ответ значит «принято»,
    // поэтому деньги покупателю возвращают уже после подтверждения.
    cancelOzon: (orderId) => api.post(`/site-orders/${orderId}/ozon/cancel/`),
};
