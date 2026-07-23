import { useState, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import { TrendingUp, TrendingDown, Download, Loader2, AlertCircle, Calendar, X, ExternalLink } from 'lucide-react';
import { FadeRise, Stagger, StaggerItem, AnimatedNumber } from '../ui/motion';
import { analysisApi } from '../../api/analysisApi';
import './CashFlowReportV2.css';

const fmtMoney = (v) => (v == null ? '0' : Math.round(v).toLocaleString('ru-RU'));

// Терракотовый тональный ряд — сегменты подписаны напрямую, доли одной метрики.
const GROUP_COLORS = ['#cc785c', '#d6987f', '#b5654c', '#e3b9a6', '#8f4a37', '#c98f6b', '#a85a44'];

// Пояснения к KPI — простыми словами, что показано и как считается.
const KPI_HINTS = {
    initial: 'Сколько денег на счетах и в кассе на начало периода. Считается от базовой точки (январь 2025 — 8 877 300 ₽) плюс все движения до начала периода.',
    income: 'Все поступления денег за период: оплаты от клиентов и возвраты. Сумма операций «Входящий платёж» и «Приходный ордер».',
    expense: 'Все траты за период: поставщикам, зарплата, налоги, аренда. Внутренние перемещения не учитываются.',
    net: 'Приход минус расход. На сколько денег стало больше или меньше за период.',
    profit: 'Приход минус расход за период. В этой версии совпадает с чистым потоком.',
    final: 'Начальный остаток плюс чистый поток. Сколько денег останется на конец периода.',
};

const prepareGroups = (source) => {
    if (!source) return [];
    return Object.entries(source)
        .map(([name, amount]) => ({ name, amount: amount || 0 }))
        .filter((r) => r.amount > 0)
        .sort((a, b) => b.amount - a.amount)
        .map((r, i) => ({ ...r, color: GROUP_COLORS[i % GROUP_COLORS.length] }));
};

const prepareSource = (source, isExpense = false) => {
    if (!source) return [];
    return Object.entries(source)
        .map(([name, data]) => {
            const amount = typeof data === 'object' ? data.amount : data;
            const link = isExpense && typeof data === 'object' ? data.moysklad_link : null;
            return { name, amount: amount || 0, link };
        })
        .filter((r) => r.amount > 0)
        .sort((a, b) => b.amount - a.amount);
};

// ─── KPI карточка с пояснением (i) ───
const StatCard = ({ label, value, hint, accent }) => {
    const cls = accent ? `cfv2-kc-v cfv2-${accent}` : 'cfv2-kc-v';
    return (
        <StaggerItem className="cfv2-kc">
            <span className="cfv2-info" tabIndex={0} aria-label={hint}>i
                <span className="cfv2-tip-static" role="tooltip"><b>{label}</b><span>{hint}</span></span>
            </span>
            <p className="cfv2-kc-l">{label}</p>
            <p className={cls}>
                <AnimatedNumber value={value || 0} format={fmtMoney} /><small> ₽</small>
            </p>
        </StaggerItem>
    );
};
StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.number,
    hint: PropTypes.string.isRequired,
    accent: PropTypes.string,
};

const CashFlowReportV2 = () => {
    const [loading, setLoading] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [progress, setProgress] = useState(0);
    const [incMode, setIncMode] = useState('grp'); // grp | src
    const [expMode, setExpMode] = useState('grp');
    const [tip, setTip] = useState(null);
    const tipRef = useRef(null);

    const fetchReport = useCallback(async () => {
        if (!dateFrom || !dateTo) { setError('Выберите период для формирования отчёта'); return; }
        setLoading(true); setError(null); setProgress(0);
        const iv = setInterval(() => setProgress((p) => (p < 90 ? p + 10 : p)), 200);
        try {
            const result = await analysisApi.cashFlow.get(dateFrom, dateTo);
            clearInterval(iv); setProgress(100);
            if (result.success) setData(result.data);
            else setError(result.error || result.message || 'Ошибка получения данных');
        } catch (err) {
            clearInterval(iv);
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
            const blob = await analysisApi.cashFlow.export(dateFrom, dateTo);
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            const ts = new Date().toISOString().slice(0, 19).replaceAll('-', '').replaceAll(':', '').replace('T', '');
            a.download = `cash_flow_report_${ts}.xlsx`;
            document.body.appendChild(a); a.click(); document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setError('Ошибка экспорта: ' + err.message);
        } finally {
            setExporting(false);
        }
    };

    // ─── плавающий тултип ───
    const periodLink = data?.moysklad_period_link || null;
    const openLink = (link) => { if (link) window.open(link, '_blank', 'noopener,noreferrer'); };
    const showTip = (e, { name, color, amount, total, link }) => {
        setTip({ name, color, amount, total, link, x: e.clientX, y: e.clientY });
    };
    const moveTip = (e) => {
        setTip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t));
    };
    const hideTip = () => setTip(null);

    const tipStyle = () => {
        if (!tip) return { opacity: 0 };
        const w = 210, h = 116, pad = 14;
        let x = tip.x + pad, y = tip.y + pad;
        if (x + w > window.innerWidth - 8) x = tip.x - w - pad;
        if (y + h > window.innerHeight - 8) y = tip.y - h - pad;
        return { left: x, top: y, opacity: 1 };
    };

    const canFetch = dateFrom && dateTo && !loading;

    const incGroups = prepareGroups(data?.income?.groups);
    const expGroups = prepareGroups(data?.expense?.groups);
    const channels = prepareSource(data?.income?.channels, false);
    const articles = prepareSource(data?.expense?.categories, true);
    const totalIncome = data?.income?.total || 0;
    const totalExpense = data?.expense?.total || 0;

    // ─── рендер разбивки внутри панели ───
    const renderBreakdown = (side) => {
        const isInc = side === 'inc';
        const mode = isInc ? incMode : expMode;
        const total = isInc ? totalIncome : totalExpense;
        if (mode === 'grp') {
            const groups = isInc ? incGroups : expGroups;
            if (!groups.length) return <p className="cfv2-empty-row">Нет данных</p>;
            const max = groups[0].amount;
            return (
                <div className="cfv2-cbody" key={`${side}-grp`}>
                    <div className="cfv2-stack">
                        {groups.map((g, i) => {
                            const pct = (g.amount / total) * 100;
                            return (
                                <span key={g.name} className="cfv2-seg"
                                    style={{ flex: g.amount, background: g.color, animationDelay: `${0.05 + i * 0.06}s`, cursor: periodLink ? 'pointer' : 'default' }}
                                    onClick={() => openLink(periodLink)}
                                    onMouseEnter={(e) => showTip(e, { name: g.name, color: g.color, amount: g.amount, total, link: periodLink })}
                                    onMouseMove={moveTip} onMouseLeave={hideTip}>
                                    {pct >= 9 && <span className="cfv2-sl">{g.name} {pct.toFixed(0)}%</span>}
                                </span>
                            );
                        })}
                    </div>
                    <Stagger className="cfv2-blist">
                        {groups.map((g) => (
                            <StaggerItem key={g.name}>
                                <div className="cfv2-brow" onClick={() => openLink(periodLink)}
                                    onMouseEnter={(e) => showTip(e, { name: g.name, color: g.color, amount: g.amount, total, link: periodLink })}
                                    onMouseMove={moveTip} onMouseLeave={hideTip}>
                                    <span className="cfv2-nm">
                                        <span className="cfv2-dot" style={{ background: g.color }} />
                                        <span className="cfv2-txt">{g.name}</span>
                                        {periodLink && <ExternalLink className="cfv2-ext" />}
                                    </span>
                                    <span className="cfv2-trk"><i style={{ width: `${Math.max((g.amount / max) * 100, 1.5)}%`, background: g.color }} /></span>
                                    <span className="cfv2-fg">{fmtMoney(g.amount)} ₽<em>{((g.amount / total) * 100).toFixed(1)}%</em></span>
                                </div>
                            </StaggerItem>
                        ))}
                    </Stagger>
                </div>
            );
        }
        // source dimension: каналы / статьи
        const rows = isInc ? channels : articles;
        const head = isInc ? 'Канал поступления' : 'Статья расходов';
        if (!rows.length) return <p className="cfv2-empty-row">Нет данных</p>;
        return (
            <div className="cfv2-cbody" key={`${side}-src`}>
                <div className="cfv2-scroll">
                    <table className="cfv2-table">
                        <thead><tr><th>{head}</th><th className="r">Сумма, ₽</th></tr></thead>
                        <tbody>
                            {rows.map((r) => {
                                const link = r.link || periodLink;
                                return (
                                    <tr key={r.name} style={{ cursor: link ? 'pointer' : 'default' }}
                                        onClick={() => openLink(link)}
                                        onMouseEnter={(e) => showTip(e, { name: r.name, color: isInc ? '#059669' : '#dc2626', amount: r.amount, total, link })}
                                        onMouseMove={moveTip} onMouseLeave={hideTip}>
                                        <td>{r.name}{link && <ExternalLink className="cfv2-ext" />}</td>
                                        <td className="num">{fmtMoney(r.amount)}</td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    };

    const net = data?.net_cash_flow || 0;

    return (
        <div className="cfv2-root">
            {/* Top bar */}
            <div className="cfv2-topbar">
                <div>
                    <h1 className="cfv2-title">Движение денежных средств</h1>
                    <p className="cfv2-sub">Приходы и расходы за период — по источникам и по группам контрагента</p>
                </div>
                <div className="cfv2-ctr">
                    <div className="filter-date-range cfv2-dates">
                        <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} disabled={loading} className="cfv2-date" />
                        <span className="filter-date-sep">—</span>
                        <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} disabled={loading} className="cfv2-date" />
                    </div>
                    {data && (
                        <button onClick={exportToExcel} disabled={exporting || loading} className="cfv2-btn s">
                            {exporting ? <Loader2 className="cfv2-ic spin" /> : <Download className="cfv2-ic" />} Excel
                        </button>
                    )}
                    <button onClick={fetchReport} disabled={!canFetch} className="cfv2-btn p">
                        {loading ? <><Loader2 className="cfv2-ic spin" />Формируется…</> : <><Calendar className="cfv2-ic" />Сформировать</>}
                    </button>
                </div>
            </div>

            {(loading || progress > 0) && (
                <div className="cfv2-progress"><div style={{ width: `${Math.min(progress, 100)}%` }} /></div>
            )}

            {error && (
                <div className="cfv2-error">
                    <AlertCircle className="cfv2-ic" style={{ color: '#c64545' }} />
                    <span>{error}</span>
                    <button onClick={() => setError(null)}><X className="cfv2-ic" /></button>
                </div>
            )}

            {!data && !loading && !error && (
                <div className="cfv2-empty">
                    <Calendar className="cfv2-empty-ic" />
                    <p className="cfv2-empty-t">Выберите период для формирования отчёта</p>
                    <p className="cfv2-empty-s">Укажите даты начала и окончания, затем нажмите «Сформировать»</p>
                </div>
            )}

            {data && (
                <>
                    {/* KPI */}
                    <Stagger className="cfv2-kpi">
                        <StatCard label="Нач. остаток" value={data.initial_balance} hint={KPI_HINTS.initial} accent="b" />
                        <StatCard label="Приход" value={data.income?.total} hint={KPI_HINTS.income} accent="g" />
                        <StatCard label="Расход" value={data.expense?.total} hint={KPI_HINTS.expense} accent="r" />
                        <StatCard label="Чистый поток" value={net} hint={KPI_HINTS.net} accent={net >= 0 ? 'g' : 'r'} />
                        <StatCard label="Прибыль" value={data.profit} hint={KPI_HINTS.profit} accent={(data.profit || 0) >= 0 ? 'g' : 'r'} />
                        <StatCard label="Кон. остаток" value={data.final_balance} hint={KPI_HINTS.final} />
                    </Stagger>

                    {/* Two panels */}
                    <div className="cfv2-main">
                        <FadeRise className="cfv2-panel">
                            <div className="cfv2-phead">
                                <span className="cfv2-plabel"><TrendingUp className="cfv2-ic up" /> Приходы <span className="cfv2-amt">{fmtMoney(totalIncome)} ₽</span></span>
                                <div className="cfv2-seg-ctl">
                                    <button aria-selected={incMode === 'grp'} onClick={() => setIncMode('grp')}>Группы</button>
                                    <button aria-selected={incMode === 'src'} onClick={() => setIncMode('src')}>Каналы</button>
                                </div>
                            </div>
                            {renderBreakdown('inc')}
                        </FadeRise>

                        <FadeRise className="cfv2-panel" delay={0.06}>
                            <div className="cfv2-phead">
                                <span className="cfv2-plabel"><TrendingDown className="cfv2-ic down" /> Расходы <span className="cfv2-amt">{fmtMoney(totalExpense)} ₽</span></span>
                                <div className="cfv2-seg-ctl">
                                    <button aria-selected={expMode === 'grp'} onClick={() => setExpMode('grp')}>Группы</button>
                                    <button aria-selected={expMode === 'src'} onClick={() => setExpMode('src')}>Статьи</button>
                                </div>
                            </div>
                            {renderBreakdown('exp')}
                        </FadeRise>
                    </div>

                    {/* Footer */}
                    <div className="cfv2-foot">
                        <div className="cfv2-fc">
                            <span className="l">Прибыль (приход − расход)</span>
                            <span className="v" style={{ color: (data.profit || 0) >= 0 ? '#059669' : '#dc2626' }}>{data.profit >= 0 ? '+' : ''}{fmtMoney(data.profit)} ₽</span>
                        </div>
                        <div className="cfv2-fc">
                            <span className="l">Конечный остаток</span>
                            <span className="v">{fmtMoney(data.final_balance)} ₽</span>
                        </div>
                    </div>
                </>
            )}

            {/* floating tooltip */}
            {tip && (
                <div className="cfv2-tip" ref={tipRef} style={tipStyle()}>
                    <div className="cfv2-tip-h"><span className="cfv2-dot" style={{ background: tip.color }} />{tip.name}</div>
                    <div className="cfv2-tip-v">{fmtMoney(tip.amount)} ₽</div>
                    <div className="cfv2-tip-s">{((tip.amount / tip.total) * 100).toFixed(1)}% от итога · {fmtMoney(tip.total)} ₽</div>
                    {tip.link && <div className="cfv2-tip-l"><ExternalLink className="cfv2-ic" /> Открыть в МойСклад</div>}
                </div>
            )}
        </div>
    );
};

export default CashFlowReportV2;
