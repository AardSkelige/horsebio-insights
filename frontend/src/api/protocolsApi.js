import api from '../utils/api';

const readBlobError = async (err) => {
    if (err.data instanceof Blob) {
        const body = await err.data.text().then(JSON.parse).catch(() => null);
        if (body?.error) throw new Error(body.error);
    }
    throw err;
};

export const protocolsApi = {
    tasks: (search, signal) => api.get('/protocols/tasks/', { params: search ? { search } : undefined, signal }),
    task: (id, signal) => api.get(`/protocols/tasks/${id}/`, { signal }),
    docx: (id, variant, rows) => api.post(`/protocols/tasks/${id}/docx/`, { variant, rows }, { responseType: 'blob' })
        .catch(readBlobError),
    linkTemplate: (templateId, plans) => api.post('/protocols/template-links/', { template_id: templateId, plans }),
    linkMaterial: (templateId, rowName, materialId) => api.post('/protocols/template-materials/', {
        template_id: templateId, row_name: rowName, material_id: materialId,
    }),
};
