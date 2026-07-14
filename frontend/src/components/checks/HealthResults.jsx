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

function FindingRow({ cat, item, excepted, onAdded }) {
    const [state, setState] = useState('idle'); // idle | reason | busy | added
    const [reason, setReason] = useState('');
    const [excId, setExcId] = useState(null);
    const c = sevOf(item.severity);
    const link = item.ms_href || msLink(cat.ms_type, item.ms_id);
    const canExcept = cat.kind && item.key;

    const add = async () => {
        setState('busy');
        try {
            const extra = cat.kind === 'deviations' ? { status: 'норма', ms_id: item.ms_id || '', ms_href: item.ms_href || '' } : {};
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
FindingRow.propTypes = { cat: PropTypes.object, item: PropTypes.object, excepted: PropTypes.bool, onAdded: PropTypes.func };

function Category({ cat, excKeys, jumpKey, onChanged }) {
    const [open, setOpen] = useState(cat.severity === 'critical' || cat.severity === 'important');
    const [hidden, setHidden] = useState(new Set());
    const c = sevOf(cat.severity);

    useEffect(() => { if (jumpKey === cat.key) setOpen(true); }, [jumpKey, cat.key]);

    // ack-типы, уже добавленные в исключения, из снимка не показываем — при следующем
    // запуске скрипт их и так не выдаст; deviations остаются (помечаются бейджем)
    const isAckExcepted = (it) => cat.kind && cat.kind !== 'deviations'
        && it.key && (excKeys[cat.kind] || []).includes(it.key);
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
                        return (
                            <FindingRow
                                key={ekey}
                                cat={cat}
                                item={it}
                                excepted={excepted}
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
Category.propTypes = { cat: PropTypes.object, excKeys: PropTypes.object, jumpKey: PropTypes.string, onChanged: PropTypes.func };

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
            {data.categories.length === 0 ? (
                Array.isArray(data.summary?.stats) && data.summary.stats.length > 0 ? (
                    <div style={{ textAlign: 'center', padding: 28, color: 'var(--muted)' }}>Изменений нет — всё актуально</div>
                ) : (
                    <div style={{ textAlign: 'center', padding: 40, color: 'var(--success)', fontWeight: 600 }}>✓ Проблем не найдено</div>
                )
            ) : (
                data.categories.map((cat) => (
                    <Category key={cat.key} cat={cat} excKeys={excKeys} jumpKey={jumpKey} onChanged={() => setRefreshKey((k) => k + 1)} />
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
