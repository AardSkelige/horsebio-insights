import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { formatDateTimeShort } from '../../utils/formatters';
import { useIsMobile } from '../../hooks/useIsMobile';
import { Download } from 'lucide-react';
import { Button, Card, EmptyState, ErrorState, Page, PageHeader, SearchInput, Toolbar } from '../ui';
import { FadeRise } from '../ui/motion';
import { analysisApi } from '../../api/analysisApi';
import FboStockTable from './FboStockTable';
import { matchesQuery, parseQuery, searchIndex } from './search';

const compare = (a, b, key) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === 'number' && typeof bv === 'number') return av - bv;
    return String(av ?? '').localeCompare(String(bv ?? ''), 'ru');
};

export default function FboStock() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [error, setError] = useState(null);
    const [search, setSearch] = useState('');
    const [showEmpty, setShowEmpty] = useState(false);
    const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
    const isMobile = useIsMobile();
    const abortRef = useRef(null);

    const load = useCallback((force = false) => {
        const controller = new AbortController();
        abortRef.current?.abort();
        abortRef.current = controller;
        setError(null);
        if (force) setRefreshing(true); else setLoading(true);
        analysisApi.fboStock.get({ refresh: force, signal: controller.signal })
            .then((res) => setData(res.data))
            .catch((err) => { if (err.name !== 'AbortError') setError(err.message || 'Не удалось загрузить остатки'); })
            .finally(() => {
                if (abortRef.current !== controller) return;
                setLoading(false);
                setRefreshing(false);
            });
    }, []);

    useEffect(() => {
        load();
        return () => abortRef.current?.abort();
    }, [load]);

    const handleExport = async () => {
        setExporting(true);
        try {
            const blob = await analysisApi.fboStock.export();
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `Остатки для FBO ${new Date().toLocaleDateString('ru-RU')}.xlsx`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch {
            // Ответ запрошен блобом, поэтому текст ошибки бэкенда в err.message не
            // доезжает — там осталась бы английская строка axios про статус-код
            setError('Не удалось выгрузить Excel. Обновите данные и попробуйте ещё раз');
        } finally {
            setExporting(false);
        }
    };

    // Индекс строится один раз на выдачу, а не на каждое нажатие клавиши
    const indexed = useMemo(
        () => (data?.items || []).map((item) => ({ item, haystack: searchIndex(item) })),
        [data],
    );

    const items = useMemo(() => {
        const parts = parseQuery(search);
        const filtered = indexed
            .filter(({ item, haystack }) => {
                if (!showEmpty && item.is_empty) return false;
                return matchesQuery(haystack, parts);
            })
            .map(({ item }) => item);
        return [...filtered].sort((a, b) => {
            const result = compare(a, b, sort.key);
            return sort.dir === 'asc' ? result : -result;
        });
    }, [indexed, search, showEmpty, sort]);

    const handleSortChange = (key) => {
        setSort((prev) => (prev.key === key
            ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
            : { key, dir: key === 'name' || key === 'article' ? 'asc' : 'desc' }));
    };

    return (
        <Page>
            <PageHeader
                title="Остатки для FBO"
                subtitle="Сколько товара можно увезти на маркетплейс сегодня — по складу готовой продукции"
                updatedAt={data?.generated_at ? formatDateTimeShort(data.generated_at) : undefined}
                onRefresh={() => load(true)}
                refreshing={refreshing || loading}
                actions={
                    <Button
                        variant="primary"
                        icon={Download}
                        loading={exporting}
                        disabled={loading || !data}
                        onClick={handleExport}
                    >
                        {exporting ? 'Готовим…' : 'Скачать Excel'}
                    </Button>
                }
            />

            {/* Главное недоразумение, ради которого страница и сделана: «Доступно» в
                МойСклад прибавляет ожидание, поэтому показывает больше, чем есть */}
            <Card tone="quiet" style={{ padding: '11px 14px', fontSize: 'var(--size-sm)', color: 'var(--muted)', lineHeight: 1.55 }}>
                <b style={{ color: 'var(--ink)', fontWeight: 500 }}>Можно взять = На складе − В резерве.</b>{' '}
                В МойСклад колонка «Доступно» прибавляет сюда ещё и ожидание — товар, который только запланирован
                к выпуску и физически на складе не лежит. Здесь ожидание вынесено отдельной колонкой и в расчёт не входит.
            </Card>

            <Toolbar>
                <SearchInput
                    value={search}
                    onChange={setSearch}
                    placeholder="Поиск: хондрофит 500, псил 150, 11-41"
                />
                <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 'var(--size-sm)', color: 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input
                        type="checkbox"
                        checked={showEmpty}
                        onChange={(e) => setShowEmpty(e.target.checked)}
                        style={{ accentColor: 'var(--primary)', width: 14, height: 14, cursor: 'pointer' }}
                    />
                    Показывать позиции без остатка
                </label>
            </Toolbar>

            {error && <ErrorState hint={error} onRetry={() => load(true)} />}

            {!error && (
                <FadeRise>
                    <FboStockTable
                        items={items}
                        loading={loading}
                        sort={sort}
                        onSortChange={handleSortChange}
                        isMobile={isMobile}
                    />
                    {!loading && items.length === 0 && (
                        <EmptyState
                            title={search ? 'Ничего не найдено' : 'Нет позиций с остатком'}
                            hint={search ? 'Попробуйте другой запрос — поиск ищет по всем частям названия и артикулу' : undefined}
                        />
                    )}
                </FadeRise>
            )}
        </Page>
    );
}
