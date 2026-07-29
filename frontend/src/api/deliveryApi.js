// src/api/deliveryApi.js
import api from '../utils/api';

export const deliveryApi = {
    // Оценка доставки. payload: { mode:'order', order, to_city } либо
    // { mode:'manual', positions:[{href, qty, name}], to_city }.
    // Успех (200) может содержать { blocked:true, missing:[...] }; ошибка → throw.
    estimate: (payload) => api.post('/delivery/estimate/', payload),

    // Поиск товаров для ручного ввода: [{ href, name, code }].
    searchProducts: (q, signal) => api.get('/delivery/products/', { params: { q }, signal }),

    // Последние заказы (не маркетплейсные): [{ id, name, counterparty, city, address, sum }].
    recentOrders: (signal) => api.get('/delivery/orders/', { signal }),

    // Подсказки канонических названий городов перевозчика: [{ name }].
    searchCities: (q, signal) => api.get('/delivery/cities/', { params: { q }, signal }),
};
