import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MotionProvider } from './motion';
import {
    Badge, Button, Card, CloseButton, DataTable, Disclosure, EmptyState, ErrorState,
    IconButton, MultiSelect, Notice, Page, PageHeader, Pagination, SearchInput,
    StatGrid, Toolbar,
} from './index';

const withProvider = (ui) => render(<MotionProvider>{ui}</MotionProvider>);

describe('Button', () => {
    it('применяет вариант и размер классами, а не инлайн-стилем', () => {
        render(<Button variant="primary" size="sm">Сохранить</Button>);
        const btn = screen.getByRole('button', { name: 'Сохранить' });
        expect(btn).toHaveClass('ui-btn', 'ui-btn--primary', 'ui-btn--sm');
    });

    it('во время загрузки блокируется', async () => {
        const onClick = vi.fn();
        render(<Button loading onClick={onClick}>Обновить</Button>);
        const btn = screen.getByRole('button');
        expect(btn).toBeDisabled();
        await userEvent.click(btn).catch(() => {});
        expect(onClick).not.toHaveBeenCalled();
    });

    it('на время загрузки показывает подпись загрузки, не теряя обычную ширину', () => {
        const { rerender, container } = render(
            <Button loadingLabel="Обновляем…">Обновить</Button>,
        );
        expect(screen.getByRole('button', { name: 'Обновить' })).toBeInTheDocument();

        rerender(<Button loading loadingLabel="Обновляем…">Обновить</Button>);
        expect(screen.getByRole('button', { name: 'Обновляем…' })).toBeInTheDocument();
        // обе подписи остаются в разметке — ширину кнопки задаёт самая длинная
        expect(container.querySelectorAll('.ui-btn__label > span')).toHaveLength(2);
    });

    it('рендерится ссылкой при as="a"', () => {
        render(<Button as="a" href="https://example.com">МойСклад</Button>);
        const link = screen.getByRole('link', { name: 'МойСклад' });
        expect(link).toHaveClass('ui-btn');
        expect(link).toHaveAttribute('href', 'https://example.com');
    });

    it('выключенная ссылка теряет href и помечается для скринридера', () => {
        const { container } = render(
            <Button as="a" href="https://example.com" disabled>МойСклад</Button>,
        );
        const link = container.querySelector('a');
        expect(link).not.toHaveAttribute('href');
        expect(link).toHaveAttribute('aria-disabled', 'true');
        expect(link).toHaveAttribute('tabindex', '-1');
    });
});

describe('PageHeader', () => {
    it('показывает заголовок, пояснение и время обновления', () => {
        render(<PageHeader title="Поставщики" subtitle="Анализ приёмок" updatedAt="14:20" />);
        expect(screen.getByRole('heading', { name: 'Поставщики' })).toBeInTheDocument();
        expect(screen.getByText('Анализ приёмок')).toBeInTheDocument();
        expect(screen.getByText('Обновлено 14:20')).toBeInTheDocument();
    });

    it('во время обновления кнопка подписана «Обновляем…»', () => {
        render(<PageHeader title="Товары" onRefresh={vi.fn()} refreshing />);
        expect(screen.getByRole('button', { name: 'Обновляем…' })).toBeInTheDocument();
    });

    it('кнопка «Обновить» появляется только с обработчиком', async () => {
        const onRefresh = vi.fn();
        const { rerender } = render(<PageHeader title="Товары" />);
        expect(screen.queryByRole('button', { name: /Обновить/ })).toBeNull();

        rerender(<PageHeader title="Товары" onRefresh={onRefresh} />);
        await userEvent.click(screen.getByRole('button', { name: /Обновить/ }));
        expect(onRefresh).toHaveBeenCalledTimes(1);
    });
});

describe('DataTable', () => {
    const COLUMNS = [
        { key: 'name', label: 'Наименование', strong: true },
        { key: 'sum', label: 'Сумма', numeric: true, render: (row) => `${row.sum} ₽` },
        { key: 'act', label: 'Детали', sortable: false, render: () => <button type="button">Открыть</button> },
    ];
    const ROWS = [
        { id: 1, name: 'Поставщик А', sum: 100 },
        { id: 2, name: 'Поставщик Б', sum: 200 },
    ];

    it('рендерит строки через описание колонок', () => {
        withProvider(<DataTable columns={COLUMNS} rows={ROWS} />);
        expect(screen.getByText('Поставщик А')).toBeInTheDocument();
        expect(screen.getByText('200 ₽')).toBeInTheDocument();
        expect(screen.getAllByRole('button', { name: 'Открыть' })).toHaveLength(2);
    });

    it('сортирует по клику, но не по колонке с sortable: false', async () => {
        const onSort = vi.fn();
        withProvider(
            <DataTable columns={COLUMNS} rows={ROWS} onSort={onSort} sortField="sum" sortOrder="desc" />,
        );

        await userEvent.click(screen.getByText('Наименование'));
        expect(onSort).toHaveBeenCalledWith('name');

        await userEvent.click(screen.getByText('Детали'));
        expect(onSort).toHaveBeenCalledTimes(1);
    });

    it('помечает отсортированную колонку для скринридера', () => {
        withProvider(
            <DataTable columns={COLUMNS} rows={ROWS} onSort={vi.fn()} sortField="sum" sortOrder="asc" />,
        );
        expect(screen.getByText('Сумма').closest('th')).toHaveAttribute('aria-sort', 'ascending');
    });

    it('показывает пустое состояние вместо строк', () => {
        withProvider(<DataTable columns={COLUMNS} rows={[]} emptyText="Ничего не найдено" />);
        expect(screen.getByText('Ничего не найдено')).toBeInTheDocument();
    });

    it('при загрузке без данных показывает скелетон, а с данными — приглушает их', () => {
        const { rerender } = withProvider(<DataTable columns={COLUMNS} rows={[]} loading />);
        expect(document.querySelectorAll('.skeleton').length).toBeGreaterThan(0);

        rerender(
            <MotionProvider>
                <DataTable columns={COLUMNS} rows={ROWS} loading />
            </MotionProvider>,
        );
        expect(screen.getByText('Поставщик А')).toBeInTheDocument();
        expect(document.querySelector('.ui-table__body--loading')).not.toBeNull();
    });
});

describe('Pagination', () => {
    it('молчит, когда всё помещается на одну страницу', () => {
        const { container } = render(
            <Pagination pagination={{ current: 1, pageSize: 10, total: 8 }} onPageChange={vi.fn()} />,
        );
        expect(container).toBeEmptyDOMElement();
    });

    it('сворачивает длинный список страниц многоточием', () => {
        render(<Pagination pagination={{ current: 1, pageSize: 10, total: 300 }} onPageChange={vi.fn()} />);
        expect(screen.getByText('…')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '30' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: '15' })).toBeNull();
    });

    it('молчит, пока total не пришёл с ответом', () => {
        const { container } = render(
            <Pagination pagination={{ current: 1, pageSize: 10 }} onPageChange={vi.fn()} />,
        );
        expect(container).toBeEmptyDOMElement();
    });

    it('сообщает текущую страницу и переключает её', async () => {
        const onPageChange = vi.fn();
        render(
            <Pagination pagination={{ current: 3, pageSize: 10, total: 100 }} onPageChange={onPageChange} />,
        );
        expect(screen.getByRole('button', { name: '3' })).toHaveAttribute('aria-current', 'page');

        await userEvent.click(screen.getByRole('button', { name: '4' }));
        expect(onPageChange).toHaveBeenCalledWith(4);
    });
});

describe('SearchInput', () => {
    it('показывает крестик только при непустом значении и очищает поле', async () => {
        const onChange = vi.fn();
        const { rerender } = render(<SearchInput value="" onChange={onChange} />);
        expect(screen.queryByRole('button', { name: 'Очистить поиск' })).toBeNull();

        rerender(<SearchInput value="насос" onChange={onChange} />);
        await userEvent.click(screen.getByRole('button', { name: 'Очистить поиск' }));
        expect(onChange).toHaveBeenCalledWith('');
    });
});

describe('Notice', () => {
    it('красит плашку токенами тона, а не склейкой цвета с прозрачностью', () => {
        render(<Notice tone="error">Сайт не принял обмен</Notice>);
        const notice = screen.getByRole('alert');
        expect(notice).toHaveClass('ui-notice', 'ui-notice--error');
        // прежняя реализация собирала границу как `${color}40` — при токене
        // это давало невалидный цвет, и граница исчезала целиком
        expect(notice.getAttribute('style') || '').not.toMatch(/var\(--[a-z-]+\)[0-9a-f]{2}/);
    });

    it('закрывается, если передан обработчик', async () => {
        const onClose = vi.fn();
        render(<Notice tone="success" onClose={onClose}>Готово</Notice>);
        await userEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
        expect(onClose).toHaveBeenCalled();
    });
});

describe('StatGrid', () => {
    it('свой style не затирает сетку', () => {
        const { container } = render(<StatGrid style={{ marginBottom: 24 }}><div>карточка</div></StatGrid>);
        const grid = container.firstChild;
        expect(grid).toHaveStyle({ display: 'grid', marginBottom: '24px' });
    });

    it('на узком экране показатели встают по две в ряд', () => {
        // Ширина колонки живёт в переменных: медиа-запрос в ui.css подменяет
        // --stat-min на --stat-min-sm, иначе на телефоне карточки шли столбиком
        const { container } = render(<StatGrid><div>карточка</div></StatGrid>);
        const grid = container.firstChild;

        expect(grid).toHaveClass('ui-statgrid');
        expect(grid.style.getPropertyValue('--stat-min')).toBe('190px');
        expect(grid.style.getPropertyValue('--stat-min-sm')).toBe('150px');
    });

    it('широкие карточки со списками не ужимаются', () => {
        const { container } = render(<StatGrid min={280}><div>топ страниц</div></StatGrid>);
        const grid = container.firstChild;

        expect(grid.style.getPropertyValue('--stat-min-sm')).toBe('280px');
    });
});

describe('IconButton', () => {
    it('без подписи остаётся доступной для скринридера', () => {
        render(<CloseButton onClick={vi.fn()} />);
        expect(screen.getByRole('button', { name: 'Закрыть' })).toBeInTheDocument();
    });

    it('требует label и прокидывает его в aria', () => {
        render(<IconButton icon={() => null} label="Удалить" tone="danger" onClick={vi.fn()} />);
        const btn = screen.getByRole('button', { name: 'Удалить' });
        expect(btn).toHaveClass('ui-icon-btn', 'ui-icon-btn--danger');
    });
});

describe('Disclosure', () => {
    it('раскрывает содержимое по клику и сообщает состояние', async () => {
        render(
            <Disclosure summary="Приёмка №1" aside="120 шт">
                <p>детали приёмки</p>
            </Disclosure>,
        );

        const head = screen.getByRole('button', { name: /Приёмка №1/ });
        expect(head).toHaveAttribute('aria-expanded', 'false');
        expect(screen.queryByText('детали приёмки')).toBeNull();

        await userEvent.click(head);
        expect(head).toHaveAttribute('aria-expanded', 'true');
        expect(screen.getByText('детали приёмки')).toBeInTheDocument();
    });

    it('слушается внешнего состояния, когда оно задано', async () => {
        const onToggle = vi.fn();
        render(<Disclosure summary="Строка" open={false} onToggle={onToggle}>тело</Disclosure>);

        await userEvent.click(screen.getByRole('button', { name: /Строка/ }));
        expect(onToggle).toHaveBeenCalledWith(true);
        // состояние ведёт родитель — сам компонент не раскрылся
        expect(screen.queryByText('тело')).toBeNull();
    });
});

describe('MultiSelect', () => {
    const OPTIONS = [
        { value: '1', label: 'Хондрофит', hint: 'ART-11' },
        { value: '2', label: 'Псиллиум', hint: 'ART-42' },
    ];

    it('ищет и по подписи, и по вспомогательной метке', async () => {
        render(<MultiSelect options={OPTIONS} value={[]} onChange={vi.fn()} placeholder="Материалы" />);

        await userEvent.click(screen.getByRole('button', { name: /Материалы/ }));
        await userEvent.type(screen.getByPlaceholderText('Поиск...'), 'ART-42');

        expect(screen.getByText('Псиллиум')).toBeInTheDocument();
        expect(screen.queryByText('Хондрофит')).toBeNull();
    });

    it('показывает свою подпись для выбранного количества', () => {
        render(
            <MultiSelect
                options={OPTIONS}
                value={['1', '2']}
                onChange={vi.fn()}
                placeholder="Материалы"
                formatSelected={(n) => `Выбрано материалов: ${n}`}
            />,
        );
        expect(screen.getByText('Выбрано материалов: 2')).toBeInTheDocument();
    });
});

describe('состояния и обёртки', () => {
    it('EmptyState показывает подсказку', () => {
        render(<EmptyState title="Пусто" hint="Измените фильтры" />);
        expect(screen.getByText('Пусто')).toBeInTheDocument();
        expect(screen.getByText('Измените фильтры')).toBeInTheDocument();
    });

    it('ErrorState объявляется как alert и даёт повтор', async () => {
        const onRetry = vi.fn();
        render(<ErrorState hint="Сеть недоступна" onRetry={onRetry} />);
        expect(screen.getByRole('alert')).toBeInTheDocument();

        await userEvent.click(screen.getByRole('button', { name: /Попробовать ещё раз/ }));
        expect(onRetry).toHaveBeenCalled();
    });

    it('Badge, Card, Page и Toolbar кладут содержимое в свои классы', () => {
        render(
            <Page>
                <Toolbar><Badge tone="warning">Скоро</Badge></Toolbar>
                <Card title="Сводка">тело</Card>
            </Page>,
        );
        expect(screen.getByText('Скоро')).toHaveClass('ui-badge', 'ui-badge--warning');
        expect(document.querySelector('.ui-page')).not.toBeNull();
        expect(document.querySelector('.ui-toolbar')).not.toBeNull();
        expect(screen.getByText('Сводка')).toHaveClass('ui-card__title');
    });
});
