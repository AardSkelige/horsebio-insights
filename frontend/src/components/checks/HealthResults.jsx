import { useState, useEffect, useCallback } from 'react';
import PropTypes from 'prop-types';
import { ChevronRight, ExternalLink, Plus, Check, Undo2, Loader2, ShieldCheck } from 'lucide-react';
import { checksApi, SEV, sevOf, msLink, relTime } from './checksShared';
import InfoTip from './InfoTip';

const SEV_LEGEND = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <div><b style={{ color: '#e07a7a' }}>Критичные</b> — срочно сломано: FIFO 0, отклонение в разы, нулевые цены.</div>
        <div><b style={{ color: '#dba35e' }}>Важные</b> — надо разобраться: отклонения FIFO 5–50%, нарушения в документах.</div>
        <div><b style={{ color: '#d6bf6a' }}>Предупреждения</b> — к сведению: скачки цен, коды товаров.</div>
    </div>
);

// Подсказки по неочевидным категориям и стат-карточкам
const CAT_HINTS = {
    deviations_normal: 'Отклонения, подтверждённые как «норма» (исключение). Остаются в отчёте для контроля, но не считаются проблемой и не попадают в «Важные».',
};
const STAT_HINTS = {
    'Уже актуальны': 'Цены уже совпадают с FIFO — обновление не требуется.',
    'Себестоимость 0': 'Товары с нулевой себестоимостью — пропущены.',
    'Нет остатков': 'Нет остатков или FIFO = 0 — пропущены.',
    'Нет отгрузки': 'Заказ есть, но отгрузки нет — возврат создать не из чего.',
    'Не ВБ/Озон': 'Заказы не от ВБ/Озон — этим монитором не обрабатываются.',
    'Уже существуют': 'Возврат по заказу уже создан ранее.',
};

function SummaryBar({ summary }) {
    const cells = [
        ['critical', summary.critical || 0],
        ['important', summary.important || 0],
        ['warning', summary.warnings || 0],
    ].filter(([, n]) => n > 0);
    return (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 18 }}>
            {cells.map(([sev, n]) => {
                const c = SEV[sev];
                return (
                    <div key={sev} style={{
                        display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
                        borderRadius: 10, background: c.bg, border: `1px solid ${c.color}22`,
                    }}>
                        <span style={numStyle(c.color, 20)}>{n}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: c.color }}>{c.label}</span>
                    </div>
                );
            })}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', borderRadius: 10, background: SEV.ok.bg, border: `1px solid ${SEV.ok.color}22` }}>
                <span style={numStyle(SEV.ok.color, 20)}>{summary.ok || 0}</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: SEV.ok.color }}>В норме</span>
            </div>
            <span style={{ display: 'inline-flex', alignItems: 'center' }}><InfoTip text={SEV_LEGEND} /></span>
        </div>
    );
}
SummaryBar.propTypes = { summary: PropTypes.object.isRequired };

const TONE = {
    ok: 'var(--success)', critical: 'var(--error)', warning: '#c47d2f', neutral: 'var(--ink)',
};
// Цифры — по дизайн-системе: сериф (Cormorant) weight 400, отрицательный трекинг, lining-nums
export const numStyle = (color, size = 28) => ({
    fontFamily: 'var(--serif)', fontSize: size, fontWeight: 400, letterSpacing: '-0.02em',
    lineHeight: 1.15, color, fontVariantNumeric: 'lining-nums', fontFeatureSettings: '"lnum" 1',
});
const statLabelStyle = {
    fontFamily: 'var(--sans)', fontSize: 11, fontWeight: 500, letterSpacing: '0.1em',
    textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8,
};
function StatsRow({ stats, onJump }) {
    return (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 18 }}>
            {stats.map((s, i) => {
                const color = TONE[s.tone] || TONE.neutral;
                const clickable = Boolean(s.cat);
                return (
                    <div key={i}
                        onClick={clickable ? () => onJump?.(s.cat) : undefined}
                        style={{
                            minWidth: 140, padding: '14px 18px', borderRadius: 12,
                            background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                            cursor: clickable ? 'pointer' : 'default',
                        }}
                        title={clickable ? 'Показать подробности ниже' : undefined}>
                        <div style={{ ...statLabelStyle, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span>{s.label}</span>
                            {clickable && <span style={{ color: 'var(--primary)' }}>↓</span>}
                            {STAT_HINTS[s.label] && <span style={{ textTransform: 'none', letterSpacing: 0 }}><InfoTip text={STAT_HINTS[s.label]} width={230} /></span>}
                        </div>
                        <div style={numStyle(color)}>{s.value}</div>
                    </div>
                );
            })}
        </div>
    );
}
StatsRow.propTypes = { stats: PropTypes.array.isRequired, onJump: PropTypes.func };

// Суть каждой проверки простым языком — подсказка «?» на плитке
const CHECK_HINTS = {
    deviations: 'Себестоимость остатка (FIFO) сравнивается с ценой последней приёмки. Сильное расхождение — возможна ошибка в документах, либо цены реально изменились.',
    negative_stock: 'Товары с минусовым остатком на складе. Так не бывает физически — значит, в документах ошибка.',
    enters: 'Оприходования на внутренних складах. Обычно товар туда попадает перемещением; оприходование — сигнал проверить, не дублируется ли остаток.',
    enter_prices: 'Свежие оприходования, где цена не совпадает с ценой приёмки на тот момент — искажают себестоимость.',
    enter_zero: 'Оприходования с нулевой ценой позиций — занижают себестоимость и прибыль считается неверно.',
    losses: 'Списания с нарушениями: без описания, с нулевой ценой или без ячейки.',
    inventories: 'Инвентаризации с расхождениями остатков или проблемами цен (нулевые, аномальные).',
    moves: 'Перемещения с нарушениями: нет ячейки, нетипичное направление, крупные без описания.',
    supplies: 'Приёмки с нарушениями: нулевые цены, неожиданный склад, доставка отдельной позицией.',
    salesreturns: 'Возвраты покупателей с нулевой себестоимостью — портят прибыль в отчётах.',
    supply_jumps: 'Цена в последней приёмке сильно отличается от средней по прошлым. Либо опечатка в документе, либо реально новые условия у поставщика.',
    codes: 'Коды товаров: отсутствующие, дублирующиеся или не по шаблону своей группы.',
    stale_drafts: 'Непроведённые документы (черновики), забытые дольше 7 дней.',
};

// Сетка статусов всех проверок хелс-чека, включая чистые: видно, что «Списания ✓»
// проверялись и проблем нет, а не просто отсутствуют в отчёте
function ChecksGrid({ checks, onJump }) {
    return (
        <div style={{
            display: 'grid', gap: 8, marginBottom: 18,
            gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))',
        }}>
            {checks.map((ch) => {
                const clean = ch.status === 'ok';
                const skipped = ch.status === 'skipped';
                const c = sevOf(ch.severity);
                const clickable = !clean && !skipped && ch.cats.length > 0;
                return (
                    <div key={ch.id}
                        onClick={clickable ? () => onJump?.(ch.cats[0]) : undefined}
                        title={clickable ? 'Показать находки ниже' : undefined}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
                            borderRadius: 10, border: '1px solid var(--hairline)',
                            background: clean ? 'rgba(93,184,114,0.06)' : skipped ? 'var(--surface-soft)' : c.bg,
                            cursor: clickable ? 'pointer' : 'default',
                            opacity: skipped ? 0.6 : 1,
                        }}>
                        {clean
                            ? <Check size={14} style={{ color: 'var(--success)', flexShrink: 0 }} />
                            : <span style={{ width: 8, height: 8, borderRadius: 999, flexShrink: 0, background: skipped ? 'var(--muted-soft)' : c.color }} />}
                        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.25, minWidth: 0 }}>
                            {ch.title}
                        </span>
                        {CHECK_HINTS[ch.id] && <InfoTip text={CHECK_HINTS[ch.id]} width={270} />}
                        <span style={{ marginLeft: 'auto', fontSize: 12, fontWeight: 700, flexShrink: 0, color: clean ? 'var(--success)' : skipped ? 'var(--muted)' : c.color }}>
                            {clean ? 'чисто' : skipped ? '—' : ch.count}
                        </span>
                    </div>
                );
            })}
        </div>
    );
}
ChecksGrid.propTypes = { checks: PropTypes.array.isRequired, onJump: PropTypes.func };

function FindingRow({ cat, item, excepted, prevReason, onAdded }) {
    const [state, setState] = useState('idle'); // idle | reason | busy | added
    const [reason, setReason] = useState('');
    const [excId, setExcId] = useState(null);
    // Скачки цен: 'once' — глушит только этот скачок (по приёмке), 'always' — товар навсегда
    const [scope, setScope] = useState('once');
    const c = sevOf(item.severity);
    const link = item.ms_href || msLink(cat.ms_type, item.ms_id);
    const canExcept = cat.kind && item.key;
    const isJump = cat.kind === 'supply_jumps';

    const add = async () => {
        setState('busy');
        try {
            let extra = {};
            if (cat.kind === 'deviations') extra = { status: 'норма', ms_id: item.ms_id || '', ms_href: item.ms_href || '' };
            if (isJump && scope === 'once' && item.last_doc) extra = { supply_doc: item.last_doc };
            const res = await checksApi.addException({
                kind: cat.kind, key: item.key, label: item.object, reason: reason.trim(), extra,
            });
            setExcId(res.exception.id);
            setState('added');
            onAdded?.();
        } catch (e) { alert(e.message); setState('reason'); }
    };

    const undo = async () => {
        if (!excId) return;
        try { await checksApi.removeException(excId); setState('idle'); setExcId(null); onAdded?.(); }
        catch (e) { alert(e.message); }
    };

    if (state === 'added') {
        return (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, padding: '9px 14px', background: SEV.ok.bg, borderRadius: 8 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
                    <Check size={15} /> Добавлено в исключения — {item.object}
                    {reason.trim() && <span style={{ color: 'var(--muted)', fontWeight: 400 }}>({reason.trim()})</span>}
                </span>
                <button onClick={undo} style={linkBtn('var(--muted)')}>
                    <Undo2 size={13} /> Отменить
                </button>
            </div>
        );
    }

    if (state === 'reason' || state === 'busy') {
        return (
            <div style={{ padding: '10px 14px', borderTop: '1px solid var(--hairline-soft)', background: 'var(--surface-soft)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', marginBottom: 7 }}>
                    В исключения: {item.object}
                </div>
                {isJump && (
                    <div style={{ display: 'flex', gap: 14, marginBottom: 8, fontSize: 12.5, color: 'var(--body)' }}>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                            <input type="radio" checked={scope === 'once'} onChange={() => setScope('once')} />
                            Разовый случай — только этот скачок (приёмка №{item.last_doc || '?'})
                        </label>
                        <label style={{ display: 'inline-flex', alignItems: 'center', gap: 5, cursor: 'pointer' }}>
                            <input type="radio" checked={scope === 'always'} onChange={() => setScope('always')} />
                            У товара всегда так — не проверять больше
                        </label>
                    </div>
                )}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, flexWrap: 'wrap' }}>
                    <textarea
                        autoFocus
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        rows={2}
                        placeholder="Причина: почему это не проблема?"
                        style={{
                            flex: 1, minWidth: 220, fontSize: 12.5, padding: '7px 9px', borderRadius: 8,
                            resize: 'vertical', border: '1px solid var(--primary)', background: 'var(--canvas)',
                            color: 'var(--body)', fontFamily: 'inherit',
                        }}
                    />
                    <div style={{ display: 'flex', gap: 6 }}>
                        <button onClick={add} disabled={state === 'busy'} style={{ ...linkBtn('var(--on-primary, #fff)'), background: 'var(--primary)', padding: '7px 12px' }}>
                            {state === 'busy' ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />} Добавить
                        </button>
                        <button onClick={() => { setState('idle'); setReason(''); }} disabled={state === 'busy'} style={{ ...linkBtn('var(--muted)'), padding: '7px 12px' }}>
                            Отмена
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div style={{
            display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12,
            padding: '10px 14px', borderTop: '1px solid var(--hairline-soft)',
        }}>
            <div style={{ minWidth: 0, display: 'flex', gap: 10 }}>
                <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color, marginTop: 6, flexShrink: 0 }} />
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>{item.object}</div>
                    <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 2, lineHeight: 1.4 }}>{item.detail}</div>
                    {prevReason && (
                        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 5, fontSize: 12, color: 'var(--success)', marginTop: 3, lineHeight: 1.4 }}>
                            <ShieldCheck size={13} style={{ flexShrink: 0, marginTop: 1 }} />
                            <span>уже разбирали: {prevReason}</span>
                        </div>
                    )}
                </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                {link && (
                    <a href={link} target="_blank" rel="noreferrer" style={linkBtn('var(--muted)')}>
                        <ExternalLink size={13} /> МС
                    </a>
                )}
                {excepted ? (
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--success)', fontWeight: 600 }}>
                        <ShieldCheck size={13} /> в исключениях
                    </span>
                ) : canExcept ? (
                    <button onClick={() => setState('reason')} style={linkBtn('var(--primary)')}>
                        <Plus size={13} /> в искл.
                    </button>
                ) : null}
            </div>
        </div>
    );
}
FindingRow.propTypes = { cat: PropTypes.object, item: PropTypes.object, excepted: PropTypes.bool, prevReason: PropTypes.string, onAdded: PropTypes.func };

function Category({ cat, excKeys, excMap, jumpKey, onChanged }) {
    const [open, setOpen] = useState(cat.severity === 'critical' || cat.severity === 'important');
    const [hidden, setHidden] = useState(new Set());
    const c = sevOf(cat.severity);

    useEffect(() => { if (jumpKey === cat.key) setOpen(true); }, [jumpKey, cat.key]);

    const excFor = (it) => (cat.kind && it.key ? (excMap[cat.kind] || {})[it.key] : undefined);

    // ack-типы, уже добавленные в исключения, из снимка не показываем — при следующем
    // запуске скрипт их и так не выдаст; deviations остаются (помечаются бейджем).
    // Скачки цен: разовое исключение прячет только скачок своей приёмки — новый скачок
    // того же товара (другая приёмка) должен быть виден.
    const isAckExcepted = (it) => {
        if (!cat.kind || cat.kind === 'deviations') return false;
        const e = excFor(it);
        if (!e) return false;
        if (cat.kind === 'supply_jumps') return !e.supply_doc || e.supply_doc === it.last_doc;
        return true;
    };
    const visible = cat.items.filter((it) => !hidden.has(it.key || it.object) && !isAckExcepted(it));
    // Все находки ушли в исключения — категория схлопывается целиком
    if (visible.length === 0) return null;

    return (
        <div id={`cat-${cat.key}`} style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12, marginBottom: 10 }}>
            <button onClick={() => setOpen((v) => !v)} style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px',
                background: 'none', border: 'none', cursor: 'pointer', textAlign: 'left',
            }}>
                <ChevronRight size={16} style={{ color: 'var(--muted-soft)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                <span style={{ width: 9, height: 9, borderRadius: 999, background: c.color }} />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>{cat.title}</span>
                {CAT_HINTS[cat.key] && <InfoTip text={CAT_HINTS[cat.key]} />}
                <span style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: c.color, background: c.bg, padding: '2px 10px', borderRadius: 999 }}>
                    {visible.length}
                </span>
            </button>
            {open && (
                <div>
                    {visible.map((it) => {
                        const ekey = it.key || it.object;
                        const excepted = cat.kind && it.key && (excKeys[cat.kind] || []).includes(it.key);
                        // Прошлый разбор этого товара: причина исключения прямо в находке
                        const prevReason = excFor(it)?.reason || '';
                        return (
                            <FindingRow
                                key={ekey}
                                cat={cat}
                                item={it}
                                excepted={excepted}
                                prevReason={prevReason}
                                onAdded={() => {
                                    // ack-типы исчезают при следующем запуске — прячем сразу;
                                    // deviations остаются (помечаются), не прячем
                                    if (cat.kind && cat.kind !== 'deviations') {
                                        setHidden((s) => new Set(s).add(ekey));
                                    }
                                    onChanged?.();
                                }}
                            />
                        );
                    })}
                </div>
            )}
        </div>
    );
}
Category.propTypes = { cat: PropTypes.object, excKeys: PropTypes.object, excMap: PropTypes.object, jumpKey: PropTypes.string, onChanged: PropTypes.func };

export default function HealthResults({ scriptId, runId, running }) {
    const [data, setData] = useState(undefined); // undefined=loading, null=нет данных
    const [refreshKey, setRefreshKey] = useState(0);
    const [jumpKey, setJumpKey] = useState(null);

    const handleJump = (key) => {
        setJumpKey(key);
        const el = document.getElementById(`cat-${key}`);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    };

    const load = useCallback(async () => {
        try {
            const res = await checksApi.results(scriptId, runId);
            setData(res.results || null);
        } catch { setData(null); }
    }, [scriptId, runId]);

    useEffect(() => { load(); }, [load, refreshKey]);

    if (data === undefined) {
        return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" /> Загрузка…</div>;
    }
    if (data === null) {
        return (
            <div style={{ textAlign: 'center', padding: 50, color: 'var(--muted)' }}>
                {running ? 'Проверка выполняется — результаты появятся после завершения…' : 'Результатов пока нет. Запустите проверку.'}
            </div>
        );
    }

    const excKeys = data.exception_keys || {};
    const excMap = data.exceptions_map || {};
    // Возвраты в пути — не находки чека, показываются отдельной карточкой на /checks
    const visibleCats = data.categories.filter((c) => c.key !== 'pending_returns');
    return (
        <div>
            {runId && (
                <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 12 }}>
                    Запуск {relTime(data.finished_at)} (исторический снимок)
                </div>
            )}
            {Array.isArray(data.summary?.stats) && data.summary.stats.length > 0
                ? <StatsRow stats={data.summary.stats} onJump={handleJump} />
                : <SummaryBar summary={data.summary || {}} />}
            {Array.isArray(data.summary?.checks) && data.summary.checks.length > 0 && (
                <ChecksGrid checks={data.summary.checks} onJump={handleJump} />
            )}
            {visibleCats.length === 0 ? (
                Array.isArray(data.summary?.stats) && data.summary.stats.length > 0 ? (
                    <div style={{ textAlign: 'center', padding: 28, color: 'var(--muted)' }}>Изменений нет — всё актуально</div>
                ) : (
                    <div style={{ textAlign: 'center', padding: 40, color: 'var(--success)', fontWeight: 600 }}>✓ Проблем не найдено</div>
                )
            ) : (
                visibleCats.map((cat) => (
                    <Category key={cat.key} cat={cat} excKeys={excKeys} excMap={excMap} jumpKey={jumpKey} onChanged={() => setRefreshKey((k) => k + 1)} />
                ))
            )}
        </div>
    );
}

function linkBtn(color) {
    return {
        display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 9px', borderRadius: 7,
        background: 'var(--surface-soft)', border: 'none', color, fontSize: 12, fontWeight: 600,
        cursor: 'pointer', textDecoration: 'none', whiteSpace: 'nowrap',
    };
}

HealthResults.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
    running: PropTypes.bool,
};
