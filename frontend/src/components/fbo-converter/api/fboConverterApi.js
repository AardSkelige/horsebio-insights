import api, { downloadBlob } from '../../../utils/api';

export const convertFboSupply = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    const blob = await api.post('/ozon/fbo-converter/convert/', formData, {
        responseType: 'blob',
    });
    const date = new Date().toISOString().slice(0, 10);
    downloadBlob(blob, `fbo_supply_${date}.xlsx`);
};
