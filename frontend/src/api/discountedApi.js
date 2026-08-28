import api from '../utils/api';

export const discountedApi = {
    getList: (params, signal) => api.get('/discounted/', { params, signal }),
    // Снимает товар с продажи на сайте обменом CommerceML — см.
    // backend/api/services/site_exchange.py. В МойСклад ничего не меняет.
    delist: (productId) => api.post(`/discounted/${productId}/delist/`),
    // Заводит карточку на сайте: фотографии основной карточки, цена, остаток,
    // тексты и SEO. Карточка создаётся скрытой — открывает её человек.
    publish: (productId) => api.post(`/discounted/${productId}/publish/`),
    // Файл импорта для админки сайта — запасной путь, когда обмен упёрся
    // в демо-лимит и молча перестал применять поля.
    csvUrl: () => `${api.defaults.baseURL}/discounted/export.csv`,
};
