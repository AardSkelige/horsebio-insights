import { useState, useCallback, useRef, useEffect } from 'react';
import { Calendar, DatabaseIcon } from 'lucide-react';
import { useLoading } from '../../../contexts/LoadingContext';
import { statsApi } from '../../../api/statsApi';

const PRESET_RANGES = [
    { label: '1 месяц', months: 1 },
    { label: '3 месяца', months: 3 },
    { label: '6 месяцев', months: 6 },
    { label: '1 год', months: 12 }
];

const formatDateWithTimezone = (dateString) => {
    const date = new Date(dateString + 'T00:00:00');
    return date.toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' });
};

const DataManagementCard = () => {
    const { isLoading, startLoading, loadingProgress, cancelLoading, currentDateRange } = useLoading();

    const initializedRef = useRef(false);
    const wasLoadingRef = useRef(false);
    const [stats, setStats] = useState(null);

    const fetchStats = useCallback(async () => {
        try {
            const d = await statsApi.get();
            if (d.status === 'success') setStats(d.stats);
        } catch { /* silent */ }
    }, []);

    useEffect(() => { fetchStats(); }, [fetchStats]);

    useEffect(() => {
        if (wasLoadingRef.current && !isLoading) fetchStats();
        wasLoadingRef.current = isLoading;
    }, [isLoading, fetchStats]);

    const [isCustomRange, setIsCustomRange] = useState(false);
    const [activeMonths, setActiveMonths] = useState(12);
    const [dateRange, setDateRange] = useState(() => {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - 12);
        return {
            startDate: startDate.toISOString().split('T')[0],
            endDate: endDate.toISOString().split('T')[0]
        };
    });

    const updateDateRange = useCallback((startDate, endDate) => {
        setDateRange({ startDate, endDate });
    }, []);

    useEffect(() => {
        if (!initializedRef.current && currentDateRange) {
            initializedRef.current = true;
            if (currentDateRange.months && !currentDateRange.startDate && !currentDateRange.endDate) {
                setIsCustomRange(false);
                setActiveMonths(currentDateRange.months);
                const endDate = new Date();
                const startDate = new Date();
                startDate.setMonth(startDate.getMonth() - currentDateRange.months);
                setDateRange({
                    startDate: startDate.toISOString().split('T')[0],
                    endDate: endDate.toISOString().split('T')[0]
                });
            } else if (currentDateRange.startDate && currentDateRange.endDate) {
                setIsCustomRange(true);
                setActiveMonths(null);
                const fmt = (s) => { try { return new Date(s).toISOString().split('T')[0]; } catch { return s; } };
                setDateRange({
                    startDate: fmt(currentDateRange.startDate),
                    endDate: fmt(currentDateRange.endDate)
                });
            }
        }
    }, [currentDateRange]);

    const handlePresetClick = useCallback((months) => {
        const endDate = new Date();
        const startDate = new Date();
        startDate.setMonth(startDate.getMonth() - months);
        setIsCustomRange(false);
        setActiveMonths(months);
        updateDateRange(startDate.toISOString().split('T')[0], endDate.toISOString().split('T')[0]);
    }, [updateDateRange]);

    const handleDateChange = (field, value) => {
        const newRange = { ...dateRange, [field]: value };
        setDateRange(newRange);
        if (newRange.startDate && newRange.endDate) updateDateRange(newRange.startDate, newRange.endDate);
    };

    const handleLoadData = async () => {
        const params = { startDate: new Date(dateRange.startDate), endDate: new Date(dateRange.endDate) };
        if (!isCustomRange && activeMonths) params.months = activeMonths;
        await startLoading(params);
    };

    const btnStyle = (active) => ({
        padding: '6px 12px',
        fontSize: '12px',
        borderRadius: '8px',
        border: 'none',
        cursor: isLoading ? 'not-allowed' : 'pointer',
        transition: 'all 150ms ease',
        backgroundColor: isLoading ? 'var(--surface-dark-elevated)' : (active ? 'var(--primary)' : 'var(--surface-dark-elevated)'),
        color: isLoading ? 'var(--muted-soft)' : (active ? '#fff' : 'var(--on-dark-soft)'),
    });

    return (
        <div style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '12px', padding: '24px' }}>
            <h3 className="text-sm font-medium mb-4 flex items-center" style={{ color: 'var(--on-dark)' }}>
                <Calendar className="w-4 h-4 mr-2" style={{ color: 'var(--on-dark-soft)' }} />
                Управление данными
            </h3>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Период */}
                <div className="lg:col-span-2">
                    <div className="text-xs font-medium mb-2 uppercase tracking-wider" style={{ color: 'var(--on-dark-soft)' }}>
                        Период загрузки данных
                    </div>
                    <div className="flex flex-wrap gap-2 mb-3">
                        {PRESET_RANGES.map(({ label, months }) => (
                            <button key={months} onClick={() => handlePresetClick(months)} type="button" disabled={isLoading}
                                style={btnStyle(!isCustomRange && months === activeMonths)}>
                                {label}
                            </button>
                        ))}
                        <button type="button" onClick={() => { setIsCustomRange(true); setActiveMonths(null); }}
                            disabled={isLoading} style={btnStyle(isCustomRange)}>
                            Произвольный период
                        </button>
                    </div>

                    {isCustomRange && (
                        <div className="grid grid-cols-2 gap-3 mb-3">
                            {[
                                { field: 'startDate', label: 'Начало', max: dateRange.endDate, min: undefined },
                                { field: 'endDate', label: 'Конец', min: dateRange.startDate, max: new Date().toISOString().split('T')[0] },
                            ].map(({ field, label, min, max }) => (
                                <div key={field}>
                                    <label className="block text-xs mb-1" style={{ color: 'var(--muted-soft)' }}>{label}</label>
                                    <input type="date" value={dateRange[field]}
                                        onChange={(e) => handleDateChange(field, e.target.value)}
                                        min={min} max={max} disabled={isLoading}
                                        style={{
                                            display: 'block', width: '100%', padding: '4px 8px', fontSize: '12px',
                                            borderRadius: '6px', border: '1px solid #252320',
                                            backgroundColor: 'var(--surface-dark-elevated)',
                                            color: isLoading ? 'var(--muted-soft)' : 'var(--on-dark)', outline: 'none',
                                        }}
                                    />
                                </div>
                            ))}
                        </div>
                    )}

                    <div className="p-2 rounded-lg" style={{ backgroundColor: 'var(--surface-dark-elevated)' }}>
                        <p className="text-xs" style={{ color: 'var(--muted-soft)' }}>
                            {formatDateWithTimezone(dateRange.startDate)} — {formatDateWithTimezone(dateRange.endDate)}
                        </p>
                    </div>
                </div>

                {/* Обновление */}
                <div className="flex flex-col">
                    <div className="flex items-center mb-3">
                        <DatabaseIcon className="w-4 h-4 mr-2" style={{ color: 'var(--on-dark-soft)' }} />
                        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: 'var(--on-dark-soft)' }}>Обновление</span>
                    </div>
                    <div className="space-y-2 text-xs mb-4 flex-1">
                        {[
                            { label: 'Авто', value: stats?.last_auto_update || 'Нет' },
                            { label: 'Ручное', value: stats?.last_manual_update || 'Нет' },
                        ].map(({ label, value }) => (
                            <div key={label} className="flex justify-between">
                                <span style={{ color: 'var(--muted-soft)' }}>{label}</span>
                                <span style={{ color: 'var(--on-dark-soft)' }}>{value}</span>
                            </div>
                        ))}
                    </div>

                    {isLoading && loadingProgress ? (
                        <div className="space-y-2">
                            <div className="rounded-lg p-2" style={{ backgroundColor: 'var(--surface-dark-elevated)' }}>
                                <div className="text-xs font-medium" style={{ color: 'var(--primary)' }}>
                                    {loadingProgress.message}
                                </div>
                                {loadingProgress.total > 0 && (
                                    <div className="text-xs mt-1" style={{ color: 'var(--muted-soft)' }}>
                                        {Math.round((loadingProgress.processed / loadingProgress.total) * 100)}%
                                    </div>
                                )}
                            </div>
                            <button onClick={cancelLoading} className="w-full flex items-center justify-center text-xs"
                                style={{ padding: '6px 12px', borderRadius: '8px', border: 'none', cursor: 'pointer', backgroundColor: '#3d1a1a', color: '#f87171' }}>
                                Остановить
                            </button>
                        </div>
                    ) : (
                        <button onClick={handleLoadData} disabled={isLoading} className="w-full flex items-center justify-center text-xs"
                            style={{
                                padding: '8px 16px', borderRadius: '8px', border: 'none',
                                cursor: isLoading ? 'not-allowed' : 'pointer',
                                backgroundColor: 'var(--primary)', color: '#fff', fontWeight: 500,
                                transition: 'background-color 150ms ease',
                            }}
                            onMouseEnter={e => !isLoading && (e.target.style.backgroundColor = 'var(--primary-active)')}
                            onMouseLeave={e => !isLoading && (e.target.style.backgroundColor = 'var(--primary)')}>
                            <DatabaseIcon className="w-3 h-3 mr-1.5" />
                            Загрузить данные
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default DataManagementCard;
