// frontend/src/api/seasonalAnalysis.js
import api from '../utils/api';

export const seasonalAnalysisApi = {
    // Получение списка продуктов с сезонным анализом
    getAnalysis: async (params = {}) => {
        return api.get('/analysis/seasonal/', {
            params: {
                category: params.category || 'A',
                period_months: params.periodMonths || 12,
                end_date: params.endDate || ''
            }
        });
    },

    // Получение детального анализа для конкретного продукта
    getProductDetails: async (productId, params = {}) => {
        return api.get(`/analysis/seasonal/products/${productId}/`, {
            params: {
                period_months: params.periodMonths || 12,
                end_date: params.endDate || ''
            }
        });
    }
};
