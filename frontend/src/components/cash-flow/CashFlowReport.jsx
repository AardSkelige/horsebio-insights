import { useState, useCallback, useEffect, useRef } from 'react';
import { num } from '../../utils/formatters';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';
import { TrendingUp, TrendingDown, Download, AlertCircle, Calendar, X, ExternalLink } from 'lucide-react';
import { Button, DateInput, Page, PageHeader, Segmented } from '../ui';
import { FadeRise, Stagger, StaggerItem, AnimatedNumber } from '../ui/motion';
import { analysisApi } from '../../api/analysisApi';
import './CashFlowReport.css';


// Локальная дата → 'YYYY-MM-DD' для input[type=date] (без сдвига по таймзоне)
const isoDate = (d) => {
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
};

// Быстрые пресеты периода — возвращают [дата_с, дата_по]
const DATE_PRESETS = [
    { label: 'Этот месяц', range: (n) => [new Date(n.getFullYear(), n.getMonth(), 1), n] },
    { label: 'Прошлый месяц', range: (n) => [new Date(n.getFullYear(), n.getMonth() - 1, 1), new Date(n.getFullYear(), n.getMonth(), 0)] },
    { label: 'Этот квартал', range: (n) => [new Date(n.getFullYear(), Math.floor(n.getMonth() / 3) * 3, 1), n] },
    { label: 'Этот год', range: (n) => [new Date(n.getFullYear(), 0, 1), n] },
    { label: 'Прошлый год', range: (n) => [new Date(n.getFullYear() - 1, 0, 1), new Date(n.getFullYear() - 1, 11, 31)] },
];

// Пока считается отчёт — лёгкие фразы (страницу смотрят Женя и начальство).
const LOADING_PHRASES = [
    'Считаем каждую копейку — даже те, что закатились под шкаф…',
    'Допрашиваем МойСклад с пристрастием…',
    'Сверяем приходы с расходами и нервами…',
    'Уговариваем цифры сойтись…',
    'Ищем, куда утекли деньги…',
    'Пересчитываем — вдруг мы разбогатели…',
    'Собираем платежи по всем углам…',
    'Проверяем, все ли клиенты заплатили…',
    'Готовим отчёт, которым не стыдно похвастаться перед начальством…',
    'Немного финансовой магии…',
];

// Терракотовый тональный ряд — сегменты подписаны напрямую, доли одной метрики.
// Оттенки одной шкалы, а не разные категории: считаются от акцента темы,
// поэтому при смене --primary диаграмма перекрашивается целиком
const GROUP_COLORS = [
    'var(--primary)',
    'color-mix(in srgb, var(--primary) 70%, var(--canvas))',
    'var(--primary-active)',
    'color-mix(in srgb, var(--primary) 45%, var(--canvas))',
    'color-mix(in srgb, var(--primary-active) 75%, var(--ink))',
    'color-mix(in srgb, var(--primary) 85%, var(--canvas))',
    'color-mix(in srgb, var(--primary-active) 88%, var(--canvas))',
];

// Пояснения к KPI — простыми словами, что показано и как считается.
const KPI_HINTS = {
    initial: 'Сколько денег на счетах и в кассе на начало периода. Считается от базовой точки (январь 2025 — 8 877 300 ₽) плюс все движения до начала периода.',
    income: 'Все поступления денег за период: оплаты от клиентов и возвраты. Сумма операций «Входящий платёж» и «Приходный ордер».',
    expense: 'Все траты за период: поставщикам, зарплата, налоги, аренда. Внутренние перемещения не учитываются.',
    net: 'Приход минус расход. На сколько денег стало больше или меньше за период.',
    profit: 'Приход минус расход за период. Совпадает с чистым потоком.',
    final: 'Начальный остаток плюс чистый поток. Сколько денег останется на конец периода.',
};

const prepareGroups = (source, links) => {
    if (!source) return [];
    return Object.entries(source)
        .map(([name, amount]) => ({ name, amount: amount || 0, link: links?.[name] || null }))
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
const StatCard = ({ label, value, hint, accent, onHint }) => {
    const cls = accent ? `cf-kc-v cf-${accent}` : 'cf-kc-v';
    const show = (e) => onHint({ title: label, text: hint, rect: e.currentTarget.getBoundingClientRect() });
    const hide = () => onHint(null);
    return (
        <StaggerItem className="cf-kc">
            <span className="cf-info" tabIndex={0} aria-label={hint}
                onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>i</span>
            <p className="cf-kc-l">{label}</p>
            <p className={cls}>
                <AnimatedNumber value={value || 0} format={num} /><small> ₽</small>
            </p>
        </StaggerItem>
    );
};
StatCard.propTypes = {
    label: PropTypes.string.isRequired,
    value: PropTypes.number,
    hint: PropTypes.string.isRequired,
    accent: PropTypes.string,
    onHint: PropTypes.func.isRequired,
};

const CashFlowReport = () => {
    const [loading, setLoading] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [dateFrom, setDateFrom] = useState('');
    const [dateTo, setDateTo] = useState('');
    const [progress, setProgress] = useState(0);
    const [incMode, setIncMode] = useState('grp'); // grp | src
    const [expMode, setExpMode] = useState('grp');
    const [activePreset, setActivePreset] = useState(null); // подсвеченный чип периода
    const [tip, setTip] = useState(null);
    const [hint, setHint] = useState(null); // подсказка KPI: {title, text, rect}
    const [phrase, setPhrase] = useState('');
    const tipRef = useRef(null);
    const [isTouch] = useState(() => typeof window !== 'undefined' && window.matchMedia?.('(hover: none)').matches);

    // на тач-устройствах закрываем прикреплённый тултип по тапу вне его
    useEffect(() => {
        if (!tip?.pinned) return undefined;
        const close = (e) => { if (!tipRef.current?.contains(e.target)) setTip(null); };
        const id = setTimeout(() => document.addEventListener('pointerdown', close), 0);
        return () => { clearTimeout(id); document.removeEventListener('pointerdown', close); };
    }, [tip?.pinned]);

    // Ротация забавных фраз во время загрузки
    useEffect(() => {
        if (!loading) return undefined;
        const pick = () => setPhrase(LOADING_PHRASES[Math.floor(Math.random() * LOADING_PHRASES.length)]);
        pick();
        const id = setInterval(pick, 1900);
        return () => clearInterval(id);
    }, [loading]);

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
        if (isTouch) return; // на тач тултип показываем по тапу, не по «ховеру»
        setTip({ name, color, amount, total, link, x: e.clientX, y: e.clientY });
    };
    const moveTip = (e) => {
        setTip((t) => (t && !t.pinned ? { ...t, x: e.clientX, y: e.clientY } : t));
    };
    const hideTip = () => setTip((t) => (t?.pinned ? t : null));
    // клик по метке: тач → прикрепить тултип (видно название + ссылка), десктоп → сразу открыть МойСклад
    const onMarkClick = (e, data) => {
        if (isTouch) {
            e.stopPropagation();
            setTip({ ...data, x: e.clientX, y: e.clientY, pinned: true });
        } else {
            openLink(data.link);
        }
    };

    const tipStyle = () => {
        if (!tip) return { opacity: 0 };
        const w = 210, h = 116, pad = 14;
        let x = tip.x + pad, y = tip.y + pad;
        if (x + w > window.innerWidth - 8) x = tip.x - w - pad;
        if (y + h > window.innerHeight - 8) y = tip.y - h - pad;
        return { left: x, top: y, opacity: 1 };
    };

    // подсказка KPI: под значком «i», зажата в границы экрана
    const hintStyle = () => {
        if (!hint) return {};
        const w = 240, pad = 8, r = hint.rect;
        let left = r.right - w;
        if (left < pad) left = pad;
        if (left + w > window.innerWidth - pad) left = window.innerWidth - pad - w;
        return { top: r.bottom + 8, left, width: w };
    };

    const applyPreset = (preset) => {
        const [from, to] = preset.range(new Date());
        setDateFrom(isoDate(from));
        setDateTo(isoDate(to));
        setActivePreset(preset.label);
    };
    // ручная правка даты сбрасывает подсветку пресета
    const onDateFrom = (e) => { setDateFrom(e.target.value); setActivePreset(null); };
    const onDateTo = (e) => { setDateTo(e.target.value); setActivePreset(null); };

    const canFetch = dateFrom && dateTo && !loading;

    const incGroups = prepareGroups(data?.income?.groups, data?.group_links);
    const expGroups = prepareGroups(data?.expense?.groups, data?.group_links);
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
            if (!groups.length) return <p className="cf-empty-row">Нет данных</p>;
            const max = groups[0].amount;
            return (
                <div className="cf-cbody" key={`${side}-grp`}>
                    <div className="cf-stack">
                        {groups.map((g, i) => {
                            const pct = (g.amount / total) * 100;
                            const link = g.link || periodLink;
                            return (
                                <span key={g.name} className="cf-seg"
                                    style={{ flex: g.amount, background: g.color, animationDelay: `${0.05 + i * 0.06}s`, cursor: link ? 'pointer' : 'default' }}
                                    onClick={(e) => onMarkClick(e, { name: g.name, color: g.color, amount: g.amount, total, link })}
                                    onMouseEnter={(e) => showTip(e, { name: g.name, color: g.color, amount: g.amount, total, link })}
                                    onMouseMove={moveTip} onMouseLeave={hideTip}>
                                    {pct >= 9 && <span className="cf-sl">{g.name} {pct.toFixed(0)}%</span>}
                                </span>
                            );
                        })}
                    </div>
                    <Stagger className="cf-blist">
                        {groups.map((g) => {
                            const link = g.link || periodLink;
                            return (
                            <StaggerItem key={g.name}>
                                <div className="cf-brow" onClick={(e) => onMarkClick(e, { name: g.name, color: g.color, amount: g.amount, total, link })}
                                    onMouseEnter={(e) => showTip(e, { name: g.name, color: g.color, amount: g.amount, total, link })}
                                    onMouseMove={moveTip} onMouseLeave={hideTip}>
                                    <span className="cf-nm">
                                        <span className="cf-dot" style={{ background: g.color }} />
                                        <span className="cf-txt">{g.name}</span>
                                        {link && <ExternalLink className="cf-ext" />}
                                    </span>
                                    <span className="cf-trk"><i style={{ width: `${Math.max((g.amount / max) * 100, 1.5)}%`, background: g.color }} /></span>
                                    <span className="cf-fg">{num(g.amount)} ₽<em>{((g.amount / total) * 100).toFixed(1)}%</em></span>
                                </div>
                            </StaggerItem>
                            );
                        })}
                    </Stagger>
                </div>
            );
        }
        // source dimension: каналы / статьи
        const rows = isInc ? channels : articles;
        const head = isInc ? 'Канал поступления' : 'Статья расходов';
        if (!rows.length) return <p className="cf-empty-row">Нет данных</p>;
        return (
            <div className="cf-cbody" key={`${side}-src`}>
                <div className="cf-scroll">
                    <table className="cf-table">
                        <thead><tr><th>{head}</th><th className="r">Сумма, ₽</th></tr></thead>
                        <tbody>
                            {rows.map((r) => {
                                const link = r.link || periodLink;
                                return (
                                    <tr key={r.name} style={{ cursor: link ? 'pointer' : 'default' }}
                                        onClick={(e) => onMarkClick(e, { name: r.name, color: isInc ? 'var(--success)' : 'var(--error)', amount: r.amount, total, link })}
                                        onMouseEnter={(e) => showTip(e, { name: r.name, color: isInc ? 'var(--success)' : 'var(--error)', amount: r.amount, total, link })}
                                        onMouseMove={moveTip} onMouseLeave={hideTip}>
                                        <td><span className="cf-cell">{r.name}{link && <ExternalLink className="cf-ext" />}</span></td>
                                        <td className="num">{num(r.amount)}</td>
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
        <Page className="cf-root">
            <PageHeader
                title="Движение денежных средств"
                subtitle="Приходы и расходы за период — по источникам и по группам контрагента"
                actions={
                    <div className="cf-ctr">
                        <div className="cf-ctr-row">
                            <div className="filter-date-range cf-dates">
                                <DateInput placeholder="Дата с" value={dateFrom} onChange={onDateFrom} disabled={loading} aria-label="Дата начала" />
                                <span className="filter-date-sep ui-date-sep">—</span>
                                <DateInput placeholder="Дата по" value={dateTo} onChange={onDateTo} disabled={loading} aria-label="Дата окончания" />
                            </div>
                            {data && (
                                <Button variant="quiet" icon={Download} loading={exporting} disabled={loading} onClick={exportToExcel}>
                                    Excel
                                </Button>
                            )}
                            <Button variant="link" icon={Calendar} loading={loading} disabled={!canFetch} onClick={fetchReport}>
                                {loading ? 'Формируется…' : 'Сформировать'}
                            </Button>
                        </div>
                        <Segmented
                            tone="plain"
                            pill={false}
                            layoutId="cf-preset"
                            value={activePreset}
                            onChange={(label) => applyPreset(DATE_PRESETS.find((p) => p.label === label))}
                            options={DATE_PRESETS.map((p) => ({ value: p.label, label: p.label }))}
                        />
                    </div>
                }
            />

            {(loading || progress > 0) && (
                <div className="cf-loadbar">
                    <div className="cf-progress"><div style={{ width: `${Math.min(progress, 100)}%` }} /></div>
                    {loading && phrase && <p className="cf-phrase">{phrase}</p>}
                </div>
            )}

            {error && (
                <div className="cf-error">
                    <AlertCircle className="cf-ic" style={{ color: 'var(--error)' }} />
                    <span>{error}</span>
                    <button onClick={() => setError(null)}><X className="cf-ic" /></button>
                </div>
            )}

            {!data && !loading && !error && (
                <div className="cf-empty">
                    <Calendar className="cf-empty-ic" />
                    <p className="cf-empty-t">Выберите период для формирования отчёта</p>
                    <p className="cf-empty-s">Укажите даты начала и окончания, затем нажмите «Сформировать»</p>
                </div>
            )}

            {data && (
                <>
                    {/* KPI */}
                    <Stagger className="cf-kpi">
                        <StatCard label="Нач. остаток" value={data.initial_balance} hint={KPI_HINTS.initial} accent="b" onHint={setHint} />
                        <StatCard label="Приход" value={data.income?.total} hint={KPI_HINTS.income} accent="g" onHint={setHint} />
                        <StatCard label="Расход" value={data.expense?.total} hint={KPI_HINTS.expense} accent="r" onHint={setHint} />
                        <StatCard label="Чистый поток" value={net} hint={KPI_HINTS.net} accent={net >= 0 ? 'g' : 'r'} onHint={setHint} />
                        <StatCard label="Прибыль" value={data.profit} hint={KPI_HINTS.profit} accent={(data.profit || 0) >= 0 ? 'g' : 'r'} onHint={setHint} />
                        <StatCard label="Кон. остаток" value={data.final_balance} hint={KPI_HINTS.final} onHint={setHint} />
                    </Stagger>

                    {/* Two panels */}
                    <div className="cf-main">
                        <FadeRise className="cf-panel">
                            <div className="cf-phead">
                                <span className="cf-plabel"><TrendingUp className="cf-ic up" /> Приходы <span className="cf-amt">{num(totalIncome)} ₽</span></span>
                                <div className="cf-seg-ctl">
                                    <button aria-selected={incMode === 'grp'} onClick={() => setIncMode('grp')}>Группы</button>
                                    <button aria-selected={incMode === 'src'} onClick={() => setIncMode('src')}>Каналы</button>
                                </div>
                            </div>
                            {renderBreakdown('inc')}
                        </FadeRise>

                        <FadeRise className="cf-panel" delay={0.06}>
                            <div className="cf-phead">
                                <span className="cf-plabel"><TrendingDown className="cf-ic down" /> Расходы <span className="cf-amt">{num(totalExpense)} ₽</span></span>
                                <div className="cf-seg-ctl">
                                    <button aria-selected={expMode === 'grp'} onClick={() => setExpMode('grp')}>Группы</button>
                                    <button aria-selected={expMode === 'src'} onClick={() => setExpMode('src')}>Статьи</button>
                                </div>
                            </div>
                            {renderBreakdown('exp')}
                        </FadeRise>
                    </div>

                    {/* Footer */}
                    <div className="cf-foot">
                        <div className="cf-fc">
                            <span className="l">Прибыль (приход − расход)</span>
                            <span className="v" style={{ color: (data.profit || 0) >= 0 ? 'var(--success)' : 'var(--error)' }}>{data.profit >= 0 ? '+' : ''}{num(data.profit)} ₽</span>
                        </div>
                        <div className="cf-fc">
                            <span className="l">Конечный остаток</span>
                            <span className="v">{num(data.final_balance)} ₽</span>
                        </div>
                    </div>
                </>
            )}

            {/* floating tooltip — портал в body: предки с transform (route-анимация)
                ломают position:fixed, из-за чего пузырь уезжал от курсора */}
            {tip && createPortal(
                <div ref={tipRef} className={`cf-tip${tip.pinned ? ' pinned' : ''}`} style={tipStyle()}>
                    <div className="cf-tip-h"><span className="cf-dot" style={{ background: tip.color }} />{tip.name}</div>
                    <div className="cf-tip-v">{num(tip.amount)} ₽</div>
                    <div className="cf-tip-s">{((tip.amount / tip.total) * 100).toFixed(1)}% от итога · {num(tip.total)} ₽</div>
                    {tip.link && (tip.pinned
                        ? <a className="cf-tip-l" href={tip.link} target="_blank" rel="noopener noreferrer"><ExternalLink className="cf-ic" /> Открыть в МойСклад</a>
                        : <div className="cf-tip-l"><ExternalLink className="cf-ic" /> Открыть в МойСклад</div>)}
                </div>,
                document.body
            )}

            {/* KPI-подсказка — портал в body, чтобы не прятаться за сайдбар/панели */}
            {hint && createPortal(
                <div className="cf-hint" style={hintStyle()}>
                    <b>{hint.title}</b><span>{hint.text}</span>
                </div>,
                document.body
            )}
        </Page>
    );
};

export default CashFlowReport;
