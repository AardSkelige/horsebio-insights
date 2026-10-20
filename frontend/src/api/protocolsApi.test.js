import { describe, expect, it, vi } from 'vitest';

vi.mock('../utils/api', () => ({ default: { post: vi.fn(), get: vi.fn() } }));

import api from '../utils/api';
import { protocolsApi } from './protocolsApi';

describe('protocolsApi.docx', () => {
    it('достаёт причину отказа из ответа-файла', async () => {
        const failure = Object.assign(new Error('Request failed with status code 400'), {
            data: new Blob([JSON.stringify({ error: 'Для этой продукции не выбран шаблон протокола' })]),
        });
        api.post.mockRejectedValue(failure);
        await expect(protocolsApi.docx('t-1', 0, [])).rejects.toThrow('Для этой продукции не выбран шаблон протокола');
    });
});
