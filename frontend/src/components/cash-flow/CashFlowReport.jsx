import { useState, useCallback } from 'react';
import PropTypes from 'prop-types';
import { TrendingUp, TrendingDown, Download, Loader2, AlertCircle, Calendar, Info, X, ExternalLink } from 'lucide-react';
import SectionLabel from '../ui/SectionLabel';
import { analysisApi } from '../../api/analysisApi';

const fmtDate = (s) => s ? s.split('-').reverse().join('.') : '';
const fmtMoney = (v) => v == null ? '0' : Math.round(v).toLocaleString('ru-RU');

const rowShape = PropTypes.shape({ name: PropTypes.string.isRequired, amount: PropTypes.number.isRequired, moysklad_link: PropTypes.string });



const btn = (primary, disabled = false) => ({
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '7px 16px', borderRadius: '8px', border: 'none', height: '36px',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
    flexShrink: 0,
});

const dateInput = {
    height: '36px', padding: '0 10px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '8px', outline: 'none', transition: 'border-color 150ms',
};

const thStyle = {
    padding: '8px 12px',
    fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500,
    letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)',
    textAlign: 'left', borderBottom: '1px solid var(--hairline)',
    backgroundColor: 'var(--canvas)', whiteSpace: 'nowrap',
};

const StatCard = ({ label, value, trend, accent }) => {
    const color = accent === 'blue' ? 'var(--primary)'
        : accent === 'green' ? '#059669'
        : accent === 'red' ? '#dc2626'
        : trend != null ? (trend >= 0 ? '#059669' : '#dc2626')
        : 'var(--on-dark)';
    const Icon = trend == null ? null : trend >= 0 ? TrendingUp : TrendingDown;

    return (
        <div style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <p style={{ fontFamily: 'var(--sans)', fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--on-dark-soft)', margin: 0 }}>
                {label}
            </p>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                {Icon && <Icon style={{ width: 14, height: 14, color, flexShrink: 0, marginBottom: '2px', alignSelf: 'center' }} />}
                <p style={{ fontFamily: 'var(--serif)', fontSize: '26px', fontWeight: 400, letterSpacing: '-0.02em', lineHeight: 1, color, margin: 0, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1' }}>
                    {fmtMoney(value)}
                </p>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--on-dark-soft)' }}>₽</span>
            </div>
        </div>
    );
};

StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.number,
    trend: PropTypes.number,
    accent: PropTypes.string,
};

const SimpleTable = ({ rows, isExpense = false }) => {
    if (!rows.length) return (
        <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', textAlign: 'center', padding: '24px 0', margin: 0 }}>
            Нет данных
        </p>
    );
    return (
        <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                    <tr>
                        <th style={thStyle}>{isExpense ? 'Статья расходов' : 'Канал поступления'}</th>
                        <th style={{ ...thStyle, textAlign: 'right', width: 160 }}>Сумма, ₽</th>
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--hairline)' }}
                            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-card)'}
                            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                        >
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>
                                {row.moysklad_link ? (
                                    <a href={row.moysklad_link} target="_blank" rel="noopener noreferrer"
                                        style={{ color: 'var(--primary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                                        onMouseEnter={e => e.currentTarget.style.textDecoration = 'underline'}
                                        onMouseLeave={e => e.currentTarget.style.textDecoration = 'none'}
                                    >
                                        {row.name}
                                        <ExternalLink style={{ width: 11, height: 11, flexShrink: 0 }} />
                                    </a>
                                ) : row.name}
                            </td>
                            <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>
                                {fmtMoney(row.amount)}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
};

SimpleTable.propTypes = {
    rows: PropTypes.arrayOf(rowShape).isRequired,
    isExpense: PropTypes.bool,
};

const prepareRows = (source, isExpense = false) => {
    if (!source) return [];
    return Object.entries(source)
        .map(([name, data]) => {
            const amount = typeof data === 'object' ? data.amount : data;
            const moysklad_link = isExpense && typeof data === 'object' ? data.moysklad_link : null;
            return { name, amount: amount || 0, moysklad_link };
        })
        .filter(r => r.amount > 0)
        .sort((a, b) => b.amount - a.amount);
};

const CashFlowReport = () => {
    const [loading, setLoading] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [progress, setProgress] = useState(0);
    const [showInfo, setShowInfo] = useState(false);

    const fetchReport = useCallback(async () => {
        if (!dateFrom || !dateTo) { setError('Выберите период для формирования отчёта'); return; }
        setLoading(true); setError(null); setProgress(0);

        const progressInterval = setInterval(() => {
            setProgress(prev => prev < 90 ? prev + 10 : prev);
        }, 200);

        try {
            const response = await analysisApi.cashFlow.get(dateFrom, dateTo);

            const contentType = response.headers.get('content-type') || '';
            if (!contentType.includes('application/json')) {
                await response.text();
                throw new Error(`Некорректный ответ сервера (${response.status})`);
            }

            const result = await response.json();
            clearInterval(progressInterval);
            setProgress(100);

            if (result.success) {
                setData(result.data);
            } else {
                setError(result.error || result.message || 'Ошибка получения данных');
            }
        } catch (err) {
            clearInterval(progressInterval);
            setError('Ошибка сети: ' + err.message);
        } finally {
            setLoading(false);
            setTimeout(() => setProgress(0), 800);
        }
    }, [dateFrom, dateTo]);

    const exportToExcel = async () => {
        if (!dateFrom || !dateTo) return;
        setExporting(true);
        try {
            const response = await analysisApi.cashFlow.export(dateFrom, dateTo);

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                const ts = new Date().toISOString().slice(0, 19).replaceAll('-', '').replaceAll(':', '').replace('T', '');
                a.download = `cash_flow_report_${ts}.xlsx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            } else {
                const ct = response.headers.get('content-type') || '';
                const err = ct.includes('application/json') ? await response.json() : {};
                setError('Ошибка экспорта: ' + (err.error || err.message || 'Неизвестная ошибка'));
            }
        } catch (err) {
            setError('Ошибка экспорта: ' + err.message);
        } finally {
            setExporting(false);
        }
    };

    const canFetch = dateFrom && dateTo && !loading;

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', color: 'var(--ink)' }}>

            {/* Header */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px' }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: 0, marginBottom: '4px' }}>
                    Движение денежных средств
                </h1>
                <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                    Анализ доходов и расходов за выбранный период
                </p>
            </div>

            {/* Controls */}
            <section>
                <SectionLabel>Период</SectionLabel>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', alignItems: 'center' }}>
                    <div className="filter-date-range" style={{ flex: '1 1 280px' }}>
                        <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} disabled={loading} style={dateInput}
                            onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                            onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                        <span className="filter-date-sep" style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', lineHeight: 1 }}>—</span>
                        <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} disabled={loading} style={dateInput}
                            onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                            onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                    </div>
                    <button onClick={fetchReport} disabled={!canFetch} style={btn(true, !canFetch)}>
                        {loading
                            ? <><Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />Формируется...</>
                            : <><Calendar style={{ width: 13, height: 13 }} />Сформировать отчёт</>
                        }
                    </button>
                    {data && (
                        <button onClick={exportToExcel} disabled={exporting || loading} style={btn(false, exporting || loading)}>
                            {exporting
                                ? <><Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />Экспорт...</>
                                : <><Download style={{ width: 13, height: 13 }} />Скачать Excel</>
                            }
                        </button>
                    )}
                </div>

                {/* Progress bar */}
                {(loading || progress > 0) && (
                    <div style={{ marginTop: '14px', height: '3px', backgroundColor: 'var(--hairline)', borderRadius: '2px', overflow: 'hidden' }}>
                        <div style={{ height: '100%', backgroundColor: 'var(--primary)', borderRadius: '2px', width: `${Math.min(progress, 100)}%`, transition: 'width 400ms ease' }} />
                    </div>
                )}

                {/* Info banner */}
                <div style={{ marginTop: '16px', backgroundColor: 'var(--surface-card)', borderRadius: '10px', border: '1px solid var(--hairline)', overflow: 'hidden' }}>
                    <button
                        onClick={() => setShowInfo(v => !v)}
                        style={{ width: '100%', background: 'none', border: 'none', padding: '12px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px' }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Info style={{ width: 14, height: 14, color: 'var(--primary)', flexShrink: 0 }} />
                            <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>
                                Базовая точка расчёта: январь 2025 (8&nbsp;877&nbsp;300,28 ₽)
                            </span>
                        </div>
                        {showInfo
                            ? <X style={{ width: 14, height: 14, color: 'var(--muted)', flexShrink: 0 }} />
                            : <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' }}>подробнее</span>
                        }
                    </button>
                    {showInfo && (
                        <div style={{ borderTop: '1px solid var(--hairline)', padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                            <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--body)', margin: 0, lineHeight: 1.55 }}>
                                Для расчёта ДДС нужна «точка отсчёта» — дата, с которой известен точный остаток денег.
                                МойСклад API предоставляет только операции, но не хранит «исходный капитал» компании.
                                За базу взят январь 2025: начальный остаток <strong>8&nbsp;877&nbsp;300,28 ₽</strong> подтверждён отчётом МойСклад.
                            </p>
                            <div style={{ backgroundColor: 'var(--surface-dark)', borderRadius: '8px', padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--on-dark-soft)', marginBottom: '4px' }}>Алгоритм</span>
                                {[
                                    'Берём базу: январь 2025 — 8 877 300,28 ₽',
                                    'Прибавляем все доходы с января до выбранного периода',
                                    'Вычитаем все расходы за тот же период',
                                    'Получаем точный остаток на начало любого месяца',
                                ].map((s, i) => (
                                    <span key={i} style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--on-dark-soft)', lineHeight: 1.5 }}>
                                        {i + 1}. {s}
                                    </span>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </section>

            {/* Error */}
            {error && (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', backgroundColor: 'rgba(198,69,69,0.08)', border: '1px solid rgba(198,69,69,0.22)', borderRadius: '10px', padding: '14px 16px' }}>
                    <AlertCircle style={{ width: 16, height: 16, color: '#c64545', flexShrink: 0, marginTop: '1px' }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: '#c64545', flex: 1 }}>{error}</span>
                    <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: '#c64545', display: 'flex', flexShrink: 0 }}>
                        <X style={{ width: 14, height: 14 }} />
                    </button>
                </div>
            )}

            {/* Empty state */}
            {!data && !loading && !error && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '64px 0', gap: '10px' }}>
                    <Calendar style={{ width: 40, height: 40, color: 'var(--hairline)' }} />
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--ink)', margin: 0 }}>Выберите период для формирования отчёта</p>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>Укажите даты начала и окончания, затем нажмите «Сформировать отчёт»</p>
                </div>
            )}

            {/* Stats */}
            {data && (
                <section>
                    <SectionLabel>
                        {fmtDate(dateFrom)} — {fmtDate(dateTo)}
                    </SectionLabel>
                    <div className="grid grid-cols-1 lg:grid-cols-4 gap-3">
                        <StatCard label="Начальный остаток" value={data.initial_balance} accent="blue" />
                        <StatCard label="Общий приход" value={data.income?.total} accent="green" />
                        <StatCard label="Общий расход" value={data.expense?.total} accent="red" />
                        <StatCard label="Чистый поток" value={data.net_cash_flow} trend={data.net_cash_flow} />
                    </div>
                </section>
            )}

            {/* Income / Expense tables */}
            {data && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <section>
                        <SectionLabel>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <TrendingUp style={{ width: 12, height: 12, color: '#059669' }} />
                                Приходы по каналам
                                <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted)', marginLeft: '4px' }}>
                                    {fmtMoney(data.income?.total)} ₽
                                </span>
                            </span>
                        </SectionLabel>
                        <SimpleTable rows={prepareRows(data.income?.channels, false)} />
                    </section>

                    <section>
                        <SectionLabel>
                            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <TrendingDown style={{ width: 12, height: 12, color: '#dc2626' }} />
                                Расходы по статьям
                                <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted)', marginLeft: '4px' }}>
                                    {fmtMoney(data.expense?.total)} ₽
                                </span>
                            </span>
                        </SectionLabel>
                        <SimpleTable rows={prepareRows(data.expense?.categories, true)} isExpense />
                    </section>
                </div>
            )}

            {/* Excluded operations */}
            {data?.excluded && Object.keys(data.excluded).length > 0 && (
                <section>
                    <SectionLabel>Исключённые операции — не учитываются в расчётах</SectionLabel>
                    <SimpleTable rows={prepareRows(data.excluded, true)} isExpense />
                </section>
            )}

            {/* Bottom summary */}
            {data && (
                <section>
                    <SectionLabel>Итог периода</SectionLabel>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        <StatCard label="Прибыль (приход − расход)" value={data.profit} trend={data.profit} />
                        <StatCard label="Конечный остаток" value={data.final_balance} trend={data.final_balance - data.initial_balance} />
                    </div>
                </section>
            )}
        </div>
    );
};

export default CashFlowReport;
