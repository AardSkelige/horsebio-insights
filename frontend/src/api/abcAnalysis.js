// src/api/abcAnalysis.js
import api from '../utils/api';

export const abcAnalysisApi = {
    getAnalysis: async (params = {}) => {
        return api.get('/analysis/abc/', {
            params: {
                period_months: params.periodMonths || 12,
                end_date: params.endDate || ''
            }
        });
    },

    getProductDetails: async (productId, params = {}) => {
        return api.get(`/analysis/abc/products/${productId}/`, {
            params: {
                period_months: params.periodMonths || 12,
                end_date: params.endDate || ''
            }
        });
    }
};
