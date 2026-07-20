import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X } from 'lucide-react';
import { FadeRise } from '../ui/motion';
import { siteOrdersApi } from '../../api/siteOrdersApi';
import SiteOrdersTable from './SiteOrdersTable';

const PAGE_SIZE = 20;

const inputStyle = {
    fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)',
    background: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: 8, padding: '7px 12px', outline: 'none',
};

function timeAgo(iso) {
    if (!iso) return null;
    const diffMin = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    if (diffMin < 1) return 'только что';
    if (diffMin < 60) return `${diffMin} мин назад`;
    const diffH = Math.round(diffMin / 60);
    return `${diffH} ч назад`;
}

export default function SiteOrdersPage() {
    const [filters, setFilters] = useState({ search: '', dateFrom: '', dateTo: '' });
    const [debouncedSearch, setDebouncedSearch] = useState('');
    const [sort, setSort] = useState({ key: 'date', dir: 'desc' });
    const [limit, setLimit] = useState(PAGE_SIZE);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [isMobile, setIsMobile] = useState(() => window.innerWidth < 768);
    const abortRef = useRef(null);

    useEffect(() => {
        const handler = () => setIsMobile(window.innerWidth < 768);
        window.addEventListener('resize', handler);
        return () => window.removeEventListener('resize', handler);
    }, []);

    useEffect(() => {
        const t = setTimeout(() => setDebouncedSearch(filters.search.trim()), 300);
        return () => clearTimeout(t);
    }, [filters.search]);

    // Смена фильтров/сортировки должна начинать с первой страницы. Раньше сброс limit
    // и запрос жили в двух отдельных эффектах — оба срабатывали в одном коммите, и
    // запрос уходил ещё со СТАРЫМ limit (React применяет setLimit только на следующем
    // рендере), а затем второй, уже правильный запрос отменял первый — но loading
    // всё равно на мгновение становился false из .finally отменённого запроса.
    // Здесь сброс и запрос — одна операция за один проход, гонки нет.
    const filterSignature = JSON.stringify([debouncedSearch, filters.dateFrom, filters.dateTo, sort]);
    const prevSignatureRef = useRef(filterSignature);

    const load = useCallback((effectiveLimit) => {
        const controller = new AbortController();
        abortRef.current?.abort();
        abortRef.current = controller;
        setLoading(true);
        setError(null);
        siteOrdersApi.getList({
            search: debouncedSearch || undefined,
            date_from: filters.dateFrom || undefined,
            date_to: filters.dateTo || undefined,
            sort: sort.key,
            dir: sort.dir,
            limit: effectiveLimit,
        }, controller.signal)
            .then(res => setData(res))
            .catch(err => { if (err.name !== 'AbortError') setError(err.message || 'Ошибка загрузки'); })
            .finally(() => {
                // Не гасим loading, если за это время успел стартовать более новый запрос
                if (abortRef.current === controller) setLoading(false);
            });
    }, [debouncedSearch, filters.dateFrom, filters.dateTo, sort]);

    useEffect(() => {
        const filterChanged = prevSignatureRef.current !== filterSignature;
        prevSignatureRef.current = filterSignature;
        const effectiveLimit = filterChanged ? PAGE_SIZE : limit;
        if (filterChanged && limit !== PAGE_SIZE) setLimit(PAGE_SIZE);
        load(effectiveLimit);
        return () => abortRef.current?.abort();
    }, [load, limit, filterSignature]);

    const handleSortChange = (key) => {
        setSort(prev => ({ key, dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc' }));
    };

    const hasFilters = filters.search || filters.dateFrom || filters.dateTo;
    const rows = data?.data?.rows || [];
    const total = data?.data?.total ?? 0;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20, color: 'var(--ink)' }}>
            <div>
                <h1 style={{
                    fontFamily: 'var(--serif)', fontWeight: 400, fontSize: isMobile ? 24 : 30,
                    letterSpacing: '-0.02em', color: 'var(--ink)', margin: '0 0 4px',
                }}>
                    Заказы сайта
                </h1>
                <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', margin: 0 }}>
                    Заказы с horse-bio.ru, разобранные из писем, и их путь в МойСклад
                </p>
            </div>

            <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 14px', background: 'var(--canvas)', border: '1px solid var(--hairline)',
                borderRadius: 8, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', flexWrap: 'wrap',
            }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'var(--success)', flexShrink: 0 }} />
                <b style={{ color: 'var(--ink)', fontWeight: 500 }}>Автоматизация работает</b>
                {data?.data?.last_checked && (
                    <>
                        <span style={{ color: 'var(--hairline)' }}>·</span>
                        <span>последняя проверка</span>
                        <span style={{ fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted-soft)' }}>
                            {timeAgo(data.data.last_checked)}
                        </span>
                    </>
                )}
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
                <div style={{ position: 'relative', flex: '1 1 220px' }}>
                    <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', pointerEvents: 'none' }} />
                    <input
                        style={{ ...inputStyle, paddingLeft: 30, width: '100%', boxSizing: 'border-box' }}
                        placeholder="Поиск по имени, телефону, №заказа"
                        value={filters.search}
                        onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                    />
                    {filters.search && (
                        <button
                            onClick={() => setFilters(f => ({ ...f, search: '' }))}
                            style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 0 }}
                        >
                            <X size={13} />
                        </button>
                    )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <input type="date" style={inputStyle} value={filters.dateFrom}
                        onChange={e => setFilters(f => ({ ...f, dateFrom: e.target.value }))} />
                    <span style={{ fontSize: 12, color: 'var(--muted)' }}>—</span>
                    <input type="date" style={inputStyle} value={filters.dateTo} min={filters.dateFrom || undefined}
                        onChange={e => setFilters(f => ({ ...f, dateTo: e.target.value }))} />
                </div>
                {hasFilters && (
                    <button
                        onClick={() => setFilters({ search: '', dateFrom: '', dateTo: '' })}
                        style={{ ...inputStyle, display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', color: 'var(--muted)' }}
                    >
                        <X size={12} /> Сбросить
                    </button>
                )}
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

            {!error && data?.status === 'no_data' && (
                <div style={{
                    padding: 48, textAlign: 'center', background: 'var(--canvas)',
                    border: '1px solid var(--hairline)', borderRadius: 10,
                    fontFamily: 'var(--sans)', fontSize: 14, color: 'var(--muted)',
                }}>
                    {data.message}
                </div>
            )}

            {!error && (data?.status === 'success' || loading) && (
                <FadeRise>
                    <SiteOrdersTable
                        rows={rows}
                        loading={loading && rows.length === 0}
                        sort={sort}
                        onSortChange={handleSortChange}
                        isMobile={isMobile}
                    />
                    {!loading && rows.length === 0 && (
                        <div style={{
                            padding: 32, textAlign: 'center', fontFamily: 'var(--sans)', fontSize: 13,
                            color: 'var(--muted)', background: 'var(--canvas)', border: '1px solid var(--hairline)',
                            borderRadius: 10, marginTop: rows.length === 0 ? -1 : 12,
                        }}>
                            {hasFilters ? 'Ничего не найдено по этим фильтрам' : 'Заказов пока нет'}
                        </div>
                    )}
                    {rows.length < total && (
                        <div style={{ display: 'flex', justifyContent: 'center', padding: 14 }}>
                            <button
                                onClick={() => setLimit(l => l + PAGE_SIZE)}
                                disabled={loading}
                                style={{
                                    fontFamily: 'var(--sans)', fontSize: 12.5, fontWeight: 500, color: 'var(--muted)',
                                    background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8,
                                    padding: '7px 16px', cursor: loading ? 'default' : 'pointer',
                                }}
                            >
                                Показать ещё ({rows.length} из {total})
                            </button>
                        </div>
                    )}
                </FadeRise>
            )}

            <div style={{
                padding: '12px 16px', borderRadius: 8, background: 'var(--surface-soft)',
                border: '1px solid var(--hairline)', fontSize: 12, color: 'var(--muted)', lineHeight: 1.5,
            }}>
                <b style={{ color: 'var(--ink)' }}>Про ручное вмешательство сотрудников:</b> если сотрудник сам доработал
                заказ в МойСклад (принял оплату, изменил комментарий) раньше автоматики — скрипт это увидит и не
                перезапишет, статус на этой странице всё равно покажет актуальное состояние.
            </div>
        </div>
    );
}
