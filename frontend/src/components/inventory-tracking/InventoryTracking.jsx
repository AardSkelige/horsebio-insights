import { useState, useEffect, useCallback, useRef } from 'react';
import { useIsMobile } from '../../hooks/useIsMobile';
import PropTypes from 'prop-types';
import { m as motion } from 'motion/react';
import { Upload } from 'lucide-react';
import { Button, Page, PageHeader } from '../ui';
import { FadeRise } from '../ui/motion';
import InventoryStatsCards from './InventoryStatsCards';
import { inventoryApi } from '../../api/inventoryApi';
import InventoryTable from './InventoryTable';
import InventoryHistoryTable from './InventoryHistoryTable';
import CellsInfoPanel from './CellsInfoPanel';

const FOLDERS = ['Все', 'Товары', 'Тара', 'Этикетки', 'Материалы'];

function formatMonthLabel(yyyyMm) {
    const [year, month] = yyyyMm.split('-');
    const d = new Date(Number(year), Number(month) - 1, 1);
    return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}

function getRecentMonths(count = 6) {
    const months = [];
    const now = new Date();
    for (let i = 0; i < count; i++) {
        const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
        months.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
    }
    return months;
}

function MonthPicker({ selected, history, onSelect, isMobile }) {
    const months = getRecentMonths(6);
    const currentStr = months[0];
    const historyMap = Object.fromEntries(
        history.map(h => [h.month_start.slice(0, 7), h])
    );

    return (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{
                fontFamily: 'var(--sans)',
                fontSize: 12,
                color: 'var(--muted)',
                flexShrink: 0,
                marginRight: 2,
            }}>
                Период:
            </span>

            {months.map(m => {
                const isCurrent = m === currentStr;
                const active = isCurrent ? selected === null : selected === m;
                const row = historyMap[m];
                const label = isCurrent
                    ? 'Текущий'
                    : isMobile
                    ? new Date(Number(m.split('-')[0]), Number(m.split('-')[1]) - 1, 1)
                        .toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' })
                    : formatMonthLabel(m);

                return (
                    <button
                        key={m}
                        onClick={() => onSelect(isCurrent ? null : m)}
                        style={{
                            position: 'relative',
                            padding: '4px 13px',
                            borderRadius: 16,
                            border: `1px solid ${active ? 'transparent' : 'var(--hairline)'}`,
                            background: 'transparent',
                            color: active ? 'var(--canvas)' : row ? 'var(--body)' : 'var(--muted)',
                            fontFamily: 'var(--sans)',
                            fontSize: 12,
                            cursor: 'pointer',
                            transition: 'color 0.15s',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 5,
                        }}
                    >
                        {active && (
                            <motion.span
                                layoutId="month-picker-pill"
                                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                                style={{ position: 'absolute', inset: -1, borderRadius: 16, background: 'var(--ink)' }}
                            />
                        )}
                        <span style={{ position: 'relative' }}>{label}</span>
                        {row && !active && (
                            <span style={{
                                color: row.pct >= 80 ? 'var(--success)' : row.pct >= 50 ? 'var(--warning)' : 'var(--error)',
                                fontSize: 11,
                                fontWeight: 500,
                            }}>
                                {row.pct}%
                            </span>
                        )}
                    </button>
                );
            })}
        </div>
    );
}

MonthPicker.propTypes = {
    selected: PropTypes.string,
    history: PropTypes.arrayOf(PropTypes.object).isRequired,
    onSelect: PropTypes.func.isRequired,
    isMobile: PropTypes.bool,
};

export default function InventoryTracking() {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [refreshing, setRefreshing] = useState(false);
    const [uploading, setUploading] = useState(false);   // false | '2/5'
    const [uploadResult, setUploadResult] = useState(null); // {ok, message}
    const [cellsLog, setCellsLog] = useState([]);
    const [error, setError] = useState(null);
    const [activeFolder, setActiveFolder] = useState('Все');
    const [selectedMonth, setSelectedMonth] = useState(null);
    // Таблицы позиций свёрнуты по умолчанию — страница иначе слишком длинная
    const [openTables, setOpenTables] = useState({ inventoried: false, 'not-inventoried': false });
    const [history, setHistory] = useState([]);
    const isMobile = useIsMobile();
    const abortRef = useRef(null);
    const fileInputRef = useRef(null);
    const uploadResultTimerRef = useRef(null);
    const inventoriedRef = useRef(null);
    const notInventoriedRef = useRef(null);

    const fetchHistory = useCallback(async () => {
        try {
            const json = await inventoryApi.getHistory();
            if (json.status === 'success') setHistory(json.data);
        } catch {
            // history is optional; ignore errors
        }
    }, []);

    const fetchCellsLog = useCallback(async () => {
        try {
            const json = await inventoryApi.getCellsLog();
            if (json.status === 'success') setCellsLog(json.data);
        } catch { /* optional */ }
    }, []);

    useEffect(() => { fetchHistory(); fetchCellsLog(); }, [fetchHistory, fetchCellsLog]);

    const fetchData = useCallback(async () => {
        if (abortRef.current) abortRef.current.abort();
        abortRef.current = new AbortController();
        setLoading(true);
        setError(null);
        try {
            const params = new URLSearchParams();
            if (selectedMonth) params.set('month', selectedMonth);
            if (activeFolder !== 'Все') params.set('folder', activeFolder);
            const json = await inventoryApi.getCurrent(params.toString(), abortRef.current.signal);
            if (json.status === 'success') {
                setData(json.data);
            } else if (json.status === 'no_data') {
                setData(null);
                setError(json.message);
            } else {
                setData(null);
                setError(json.message || json.error || 'Ошибка сервера');
            }
        } catch (e) {
            if (e.name !== 'AbortError') setError('Ошибка загрузки данных');
        } finally {
            setLoading(false);
        }
    }, [activeFolder, selectedMonth]);

    useEffect(() => {
        fetchData();
        return () => { if (abortRef.current) abortRef.current.abort(); };
    }, [fetchData]);

    const showUploadResult = (ok, okLines = [], errLines = []) => {
        if (uploadResultTimerRef.current) clearTimeout(uploadResultTimerRef.current);
        setUploadResult({ ok, okLines: Array.isArray(okLines) ? okLines : [okLines], errLines: Array.isArray(errLines) ? errLines : [] });
        uploadResultTimerRef.current = setTimeout(() => setUploadResult(null), 8000);
    };

    const handleUploadCells = async (e) => {
        const files = Array.from(e.target.files || []);
        if (!fileInputRef.current) return;
        fileInputRef.current.value = '';
        if (!files.length) return;

        const results = { ok: [], err: [] };

        for (let i = 0; i < files.length; i++) {
            setUploading(`${i + 1}/${files.length}`);
            try {
                const json = await inventoryApi.uploadCells(files[i], null); // month from file
                if (json.status === 'success') {
                    results.ok.push(json.message);
                } else {
                    results.err.push(`${files[i].name}: ${json.message}`);
                }
            } catch {
                results.err.push(`${files[i].name}: ошибка соединения`);
            }
        }

        setUploading(false);

        if (results.ok.length && !results.err.length) {
            showUploadResult(true,
                files.length === 1
                    ? results.ok[0]
                    : `Загружено ${results.ok.length} из ${files.length} файлов`
            );
        } else if (results.err.length && !results.ok.length) {
            showUploadResult(false, results.err);
        } else {
            showUploadResult(true, results.ok, results.err);
        }

        await fetchData();
        fetchHistory();
        fetchCellsLog();
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            const json = await inventoryApi.refresh(selectedMonth);
            if (json.status !== 'success') {
                setError(json.message || 'Ошибка обновления');
            } else {
                await fetchData();
                fetchHistory();
            }
        } catch {
            setError('Ошибка соединения при обновлении');
        } finally {
            setRefreshing(false);
        }
    };

    const allProducts = data?.products || [];

    const byDaysDesc = (a, b) => {
        const da = a.days_since_last ?? Infinity;
        const db = b.days_since_last ?? Infinity;
        return db - da;
    };

    const inventoried = allProducts.filter(p => p.is_inventoried).sort(byDaysDesc);
    const notInventoried = allProducts.filter(p => !p.is_inventoried).sort(byDaysDesc);

    const currentMonthLabel = (() => {
        if (data?.month_start) return formatMonthLabel(data.month_start.slice(0, 7));
        if (selectedMonth) return formatMonthLabel(selectedMonth);
        const now = new Date();
        return formatMonthLabel(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);
    })();

    const periodLabel = (() => {
        if (data?.month_start) {
            const m = data.month_start.slice(0, 7);
            return `Период: ${formatMonthLabel(m)}`;
        }
        if (selectedMonth) return `Период: ${formatMonthLabel(selectedMonth)}`;
        return 'Мониторинг позиций за текущий месяц';
    })();

    const btnLabel = selectedMonth && !isMobile
        ? `Загрузить ${formatMonthLabel(selectedMonth)}`
        : 'Обновить';

    return (
        <Page style={{ paddingBottom: 48 }}>
            <PageHeader
                title="Инвентаризация"
                subtitle={periodLabel}
                updatedAt={data?.run_at && !isMobile
                    ? new Date(data.run_at).toLocaleString('ru-RU', {
                        day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
                    })
                    : undefined}
                onRefresh={handleRefresh}
                refreshing={refreshing}
                refreshLabel={btnLabel}
                refreshingLabel="Запрос в МС…"
                actions={
                    <>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".xls"
                            multiple
                            style={{ display: 'none' }}
                            onChange={handleUploadCells}
                        />
                        <Button
                            variant="secondary"
                            icon={Upload}
                            loading={Boolean(uploading)}
                            disabled={refreshing || loading}
                            onClick={() => fileInputRef.current?.click()}
                            title="Печать → «Инвентаризация с ячейками» — выберите один или несколько .xls файлов"
                        >
                            {uploading ? `Файл ${uploading}...` : 'С ячейками'}
                        </Button>

                    </>
                }
            />

            {/* ── Month picker ── */}
            <MonthPicker
                selected={selectedMonth}
                history={history}
                onSelect={setSelectedMonth}
                isMobile={isMobile}
            />

            {/* ── Cells info panel ── */}
            <CellsInfoPanel
                cellsLog={cellsLog}
                selectedMonth={selectedMonth}
                isMobile={isMobile}
            />

            {/* ── Upload result banner ── */}
            {uploadResult && (
                <FadeRise style={{
                    background: uploadResult.ok ? 'var(--success-bg)' : 'var(--error-bg)',
                    border: `1px solid ${uploadResult.ok ? 'var(--success-border)' : 'var(--error-border)'}`,
                    borderRadius: 8,
                    padding: '10px 16px',
                    fontFamily: 'var(--sans)',
                    fontSize: 13,
                    marginBottom: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                }}>
                    {uploadResult.okLines.map((msg, i) => (
                        <span key={i} style={{ color: 'var(--success)' }}>{msg}</span>
                    ))}
                    {uploadResult.errLines.map((msg, i) => (
                        <span key={i} style={{ color: 'var(--error)' }}>{msg}</span>
                    ))}
                </FadeRise>
            )}

            {/* ── Error banners ── */}
            {error && !data && (
                <div style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--hairline)',
                    borderRadius: 12,
                    padding: '32px 24px',
                    textAlign: 'center',
                }}>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: 15, color: 'var(--body)', margin: '0 0 8px' }}>
                        Данные ещё не загружены
                    </p>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', margin: 0 }}>
                        Нажмите «Обновить» — скрипт запросит МойСклад и сохранит результат
                    </p>
                </div>
            )}
            {error && data && (
                <div style={{
                    background: 'var(--error-bg)',
                    border: '1px solid var(--error-border)',
                    borderRadius: 8,
                    padding: '12px 16px',
                    fontFamily: 'var(--sans)',
                    fontSize: 13,
                    color: 'var(--error)',
                }}>
                    {error}
                </div>
            )}

            {/* ── Stats ── */}
            {data && (
                <FadeRise>
                    <InventoryStatsCards
                        data={data}
                        isMobile={isMobile}
                        onScrollTo={(type) => {
                            // Сначала раскрываем таблицу, потом скроллим к ней
                            setOpenTables(t => ({ ...t, [type]: true }));
                            const ref = type === 'inventoried' ? inventoriedRef : notInventoriedRef;
                            setTimeout(() => ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
                        }}
                    />
                </FadeRise>
            )}

            {/* ── Folder filter ── */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                {FOLDERS.map(folder => {
                    const active = activeFolder === folder;
                    return (
                        <button
                            key={folder}
                            onClick={() => setActiveFolder(folder)}
                            style={{
                                padding: '5px 14px',
                                borderRadius: 20,
                                border: `1px solid ${active ? 'var(--primary)' : 'var(--hairline)'}`,
                                background: active ? 'var(--primary)' : 'transparent',
                                color: active ? 'var(--on-primary)' : 'var(--body)',
                                fontFamily: 'var(--sans)',
                                fontSize: 13,
                                fontWeight: active ? 500 : 400,
                                cursor: 'pointer',
                                transition: 'all 0.15s',
                            }}
                        >
                            {folder}
                        </button>
                    );
                })}
            </div>

            {/* ── Product tables ── */}
            {(loading || data) && (
                <>
                    <FadeRise delay={0.05}>
                        <div ref={inventoriedRef} style={{ scrollMarginTop: 16 }}>
                            <InventoryTable
                                title={`Были в инвентаризации · ${currentMonthLabel}`}
                                products={inventoried}
                                type="inventoried"
                                loading={loading}
                                isMobile={isMobile}
                                open={openTables.inventoried}
                                onToggle={() => setOpenTables(t => ({ ...t, inventoried: !t.inventoried }))}
                            />
                        </div>
                    </FadeRise>
                    <FadeRise delay={0.1}>
                        <div ref={notInventoriedRef} style={{ scrollMarginTop: 16 }}>
                            <InventoryTable
                                title={`Не были в инвентаризации · ${currentMonthLabel}`}
                                products={notInventoried}
                                type="not-inventoried"
                                loading={loading}
                                isMobile={isMobile}
                                open={openTables['not-inventoried']}
                                onToggle={() => setOpenTables(t => ({ ...t, 'not-inventoried': !t['not-inventoried'] }))}
                            />
                        </div>
                    </FadeRise>
                </>
            )}

            {/* ── Monthly history ── */}
            {history.length > 0 && (
                <FadeRise inView>
                    <InventoryHistoryTable
                        history={history}
                        selectedMonth={selectedMonth}
                        onSelectMonth={setSelectedMonth}
                        isMobile={isMobile}
                    />
                </FadeRise>
            )}
        </Page>
    );
}
