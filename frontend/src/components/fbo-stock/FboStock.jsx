import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Download, RefreshCw, Search, X } from 'lucide-react';
import { FadeRise } from '../ui/motion';
import { analysisApi } from '../../api/analysisApi';
import FboStockTable from './FboStockTable';

const controlStyle = {
    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)',
    background: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: 8, padding: '7px 12px', outline: 'none',
};

const compare = (a, b, key) => {
    const av = a[key];
    const bv = b[key];
    if (typeof av === 'number' && typeof bv === 'number') return av - bv;
    return String(av ?? '').localeCompare(String(bv ?? ''), 'ru');
};

function formatTime(iso) {
    if (!iso) return null;
    return new Date(iso).toLocaleString('ru-RU', {
        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
    });
}

export default function FboStock() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [error, setError] = useState(null);
    const [search, setSearch] = useState('');
    const [showEmpty, setShowEmpty] = useState(false);
    const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
    const abortRef = useRef(null);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

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

    const items = useMemo(() => {
        const all = data?.items || [];
        const query = search.trim().toLowerCase();
        const filtered = all.filter((item) => {
            if (!showEmpty && item.is_empty) return false;
            if (!query) return true;
            return item.name.toLowerCase().includes(query)
                || item.article.toLowerCase().includes(query)
                || item.code.toLowerCase().includes(query);
        });
        return [...filtered].sort((a, b) => {
            const result = compare(a, b, sort.key);
            return sort.dir === 'asc' ? result : -result;
        });
    }, [data, search, showEmpty, sort]);

    const handleSortChange = (key) => {
        setSort((prev) => (prev.key === key
            ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
            : { key, dir: key === 'name' || key === 'article' ? 'asc' : 'desc' }));
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18, color: 'var(--ink)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16, flexWrap: 'wrap' }}>
                <div>
                    <h1 style={{
                        fontFamily: 'var(--serif)', fontWeight: 400, fontSize: isMobile ? 24 : 30,
                        letterSpacing: '-0.02em', margin: '0 0 4px',
                    }}>
                        Остатки для FBO
                    </h1>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', margin: 0 }}>
                        Сколько товара можно увезти на маркетплейс сегодня — по складу готовой продукции
                        {data?.generated_at && (
                            <>
                                {' · '}
                                {/* Ответ кешируется на 5 минут, поэтому время данных важнее любой другой сводки */}
                                <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted-soft)' }}>
                                    данные на {formatTime(data.generated_at)}
                                </span>
                            </>
                        )}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <button
                        onClick={() => load(true)}
                        disabled={refreshing || loading}
                        style={{ ...controlStyle, display: 'flex', alignItems: 'center', gap: 6, cursor: refreshing ? 'default' : 'pointer', color: 'var(--muted)' }}
                    >
                        <RefreshCw size={13} style={refreshing ? { animation: 'spin 1s linear infinite' } : undefined} />
                        Обновить
                    </button>
                    <button
                        onClick={handleExport}
                        disabled={exporting || loading || !data}
                        style={{
                            ...controlStyle, display: 'flex', alignItems: 'center', gap: 6,
                            background: 'var(--primary)', borderColor: 'var(--primary)', color: 'var(--on-primary)',
                            fontWeight: 500, cursor: exporting ? 'default' : 'pointer',
                        }}
                    >
                        <Download size={13} />
                        {exporting ? 'Готовим…' : 'Скачать Excel'}
                    </button>
                </div>
            </div>

            {/* Главное недоразумение, ради которого страница и сделана: «Доступно» в
                МойСклад прибавляет ожидание, поэтому показывает больше, чем есть */}
            <div style={{
                padding: '11px 14px', borderRadius: 8, background: 'var(--surface-soft)',
                border: '1px solid var(--hairline)', fontSize: 12.5, color: 'var(--muted)', lineHeight: 1.55,
            }}>
                <b style={{ color: 'var(--ink)', fontWeight: 500 }}>Можно взять = На складе − В резерве.</b>{' '}
                В МойСклад колонка «Доступно» прибавляет сюда ещё и ожидание — товар, который только запланирован
                к выпуску и физически на складе не лежит. Здесь ожидание вынесено отдельной колонкой и в расчёт не входит.
            </div>

            <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', flex: '1 1 240px' }}>
                    <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
                    <input
                        style={{ ...controlStyle, paddingLeft: 30, width: '100%', boxSizing: 'border-box' }}
                        placeholder="Поиск по артикулу или названию"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                    />
                    {search && (
                        <button
                            onClick={() => setSearch('')}
                            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}
                        >
                            <X size={13} />
                        </button>
                    )}
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 12.5, color: 'var(--muted)', cursor: 'pointer', userSelect: 'none' }}>
                    <input
                        type="checkbox"
                        checked={showEmpty}
                        onChange={(e) => setShowEmpty(e.target.checked)}
                        style={{ accentColor: 'var(--primary)', width: 14, height: 14, cursor: 'pointer' }}
                    />
                    Показывать позиции без остатка
                </label>
            </div>

            {error && (
                <div style={{
                    padding: 16, borderRadius: 10, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--error)',
                    background: 'color-mix(in srgb, var(--error) 8%, transparent)',
                    border: '1px solid color-mix(in srgb, var(--error) 25%, transparent)',
                }}>
                    {error}
                </div>
            )}

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
                        <div style={{
                            padding: 32, textAlign: 'center', fontFamily: 'var(--sans)', fontSize: 13,
                            color: 'var(--muted)', background: 'var(--canvas)', border: '1px solid var(--hairline)',
                            borderRadius: 10, marginTop: 12,
                        }}>
                            {search ? 'Ничего не найдено' : 'Нет позиций с остатком'}
                        </div>
                    )}
                </FadeRise>
            )}
        </div>
    );
}
