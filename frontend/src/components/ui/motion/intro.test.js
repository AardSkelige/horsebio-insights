import { beforeEach, describe, expect, it, vi } from 'vitest';

const load = async () => {
    vi.resetModules();
    return import('./intro');
};

const setReduced = (reduced) => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: reduced });
};

describe('вступление главной', () => {
    beforeEach(() => {
        setReduced(false);
    });

    it('при загрузке страницы на главной играет целиком, с сайдбаром', async () => {
        const { introFor, introFull } = await load();

        expect(introFor('/', true)).toBe(true);
        expect(introFull()).toBe(true);
    });

    it('при переходе на главную внутри приложения играет без сайдбара', async () => {
        const { introFor, introFull } = await load();
        introFor('/shipments', true);

        expect(introFor('/', false)).toBe(true);
        expect(introFull()).toBe(false);
    });

    it('на других разделах не играет, а досмотренная сцена не перезапускается от повторного рендера', async () => {
        const { introFor, endIntro } = await load();

        expect(introFor('/shipments', true)).toBe(false);
        introFor('/', false);
        endIntro();
        expect(introFor('/', false)).toBe(false);
    });

    it('после входа каркас появляется заново, и сцена снова полная', async () => {
        const { introFor, introFull } = await load();
        introFor('/profile', true);

        expect(introFor('/', true)).toBe(true);
        expect(introFull()).toBe(true);
    });

    it('не играет при уменьшенном движении', async () => {
        setReduced(true);

        expect((await load()).introFor('/', true)).toBe(false);
    });
});
