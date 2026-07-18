// src/components/ozon-analytics/api/ozonApi.js
import api, { downloadBlob } from '../../../utils/api';

export const exportAdvertisingData = async (startDate, endDate) => {
    const blob = await api.get('/ozon/advertising/export/', {
        params: { startDate, endDate },
        responseType: 'blob',
    });
    downloadBlob(blob, `advertising_${startDate}_${endDate}.xlsx`);
};

export const exportSalesData = async (startDate, endDate) => {
    const blob = await api.get('/ozon/sales/export/', {
        params: { startDate, endDate },
        responseType: 'blob',
    });
    downloadBlob(blob, `sales_${startDate}_${endDate}.xlsx`);
};

export const generateReport = async (adsFile, productsFile) => {
    const formData = new FormData();
    formData.append('ads_file', adsFile);
    formData.append('products_file', productsFile);

    const blob = await api.post('/ozon/report/', formData, {
        responseType: 'blob',
    });

    downloadBlob(blob, `DRR_отчет_эффективность_рекламы_${new Date().toISOString().slice(0, 10)}.xlsx`);
};

export const processCompetitorsInfo = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const blob = await api.post('/ozon/competitors/process/', formData, {
            responseType: 'blob',
        });

        downloadBlob(blob, `competitors_info_${new Date().toISOString().slice(0, 10)}.xlsx`);
        return true;
    } catch (error) {
        console.error('Ошибка при обработке информации о конкурентах:', error);
        throw error;
    }
};

export const processStockAvailability = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const blob = await api.post('/ozon/stock/process/', formData, {
            responseType: 'blob',
        });

        downloadBlob(blob, `stock_availability_${new Date().toISOString().slice(0, 10)}.xlsx`);
        return true;
    } catch (error) {
        console.error('Ошибка при обработке информации о доступности товаров:', error);
        throw error;
    }
};
