import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useParams } from 'react-router-dom';
import ScanButton from './ScanButton';

function OpenedSlot() {
    return <p>Открыта ячейка {useParams().slot}</p>;
}

const renderButton = () => render(
    <MemoryRouter initialEntries={['/raw-materials']}>
        <Routes>
            <Route path="/raw-materials" element={<ScanButton slots={['B2', 'А1', 'A10']} />} />
            <Route path="/raw-materials/slot/:slot" element={<OpenedSlot />} />
        </Routes>
    </MemoryRouter>,
);

const withCamera = (getUserMedia) => Object.defineProperty(navigator, 'mediaDevices', { value: { getUserMedia }, configurable: true });

describe('Кнопка «Сканировать»', () => {
    afterEach(() => {
        delete navigator.mediaDevices;
        vi.restoreAllMocks();
    });

    it('без разрешения на камеру объясняет, что делать, и даёт выбрать ячейку руками', async () => {
        vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({});
        withCamera(vi.fn().mockRejectedValue(Object.assign(new Error('denied'), { name: 'NotAllowedError' })));
        const user = userEvent.setup();
        renderButton();
        await user.click(screen.getByRole('button', { name: 'Сканировать' }));

        const sheet = within(screen.getByRole('dialog', { name: 'Сканировать QR' }));
        expect(await sheet.findByText(/Нет доступа к камере/)).toBeInTheDocument();
        expect(sheet.getAllByRole('button').map((b) => b.textContent).filter((t) => t !== '')).toEqual(['А1', 'A10', 'B2']);

        await user.click(sheet.getByRole('button', { name: 'А1' }));
        expect(await screen.findByText('Открыта ячейка А1')).toBeInTheDocument();
    });

    it('там, где камеры нет совсем, говорит об этом', async () => {
        const user = userEvent.setup();
        renderButton();
        await user.click(screen.getByRole('button', { name: 'Сканировать' }));
        expect(await screen.findByText(/Камера недоступна/)).toBeInTheDocument();
    });
});
