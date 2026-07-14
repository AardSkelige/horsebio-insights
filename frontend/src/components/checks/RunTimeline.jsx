import { useState, useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import { CheckCircle, AlertCircle, Loader2, Trash2 } from 'lucide-react';
import { SEV, relTime, fmtDuration } from './checksShared';

const TRASH_W = 64;                 // ширина кнопки-корзины
const SWIPE_OPEN = TRASH_W + 8;     // сдвиг карточки: корзина + зазор

function DeltaBadge({ delta, changed }) {
    if (!changed) {
        return <span style={{ fontSize: 11.5, color: 'var(--muted-soft)' }}>без изменений</span>;
    }
    if (!delta) {
        return <span style={{ fontSize: 11.5, color: 'var(--muted-soft)' }}>нет предыдущего запуска для сравнения</span>;
    }
    const parts = [];
    for (const sev of ['critical', 'important', 'warning']) {
        const key = sev === 'warning' ? 'warnings' : sev;
        const v = delta[key];
        if (v) {
            const improved = v < 0; // меньше находок — стало лучше
            parts.push(
                <span key={sev} style={{ color: improved ? 'var(--success)' : SEV[sev].color, fontWeight: 600 }}>
                    {improved ? '↓' : '↑'}{Math.abs(v)} {SEV[sev].label.toLowerCase()}
                </span>
            );
        }
    }
    if (!parts.length) return <span style={{ fontSize: 11.5, color: 'var(--muted-soft)' }}>изменения в составе находок</span>;
    return <span style={{ fontSize: 11.5, display: 'inline-flex', gap: 8, flexWrap: 'wrap' }}>{parts}</span>;
}
DeltaBadge.propTypes = { delta: PropTypes.object, changed: PropTypes.bool };

function HealthCounts({ summary }) {
    return (
        <span style={{ display: 'inline-flex', gap: 8 }}>
            {['critical', 'important', 'warning'].map((sev) => {
                const key = sev === 'warning' ? 'warnings' : sev;
                const n = summary?.[key] || 0;
                return (
                    <span key={sev} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12.5, color: n ? SEV[sev].color : 'var(--muted-soft)', fontWeight: n ? 600 : 400 }}>
                        <span style={{ width: 7, height: 7, borderRadius: 999, background: n ? SEV[sev].color : 'var(--muted-soft)' }} />{n}
                    </span>
                );
            })}
        </span>
    );
}
HealthCounts.propTypes = { summary: PropTypes.object };

function TimelineRow({ run, kind, active, isLast, openId, onOpenChange, onSelect, onDelete }) {
    const ok = run.exit_code === 0 || run.exit_code == null;
    const [dx, setDx] = useState(0);
    const [dragging, setDragging] = useState(false);
    const [hover, setHover] = useState(false);
    const touch = useRef(null);
    const dxRef = useRef(0);
    const applyDx = (v) => { dxRef.current = v; setDx(v); };

    // Свайпнули другую карточку — эта закрывается (как в iOS, открыта одна)
    useEffect(() => {
        if (openId !== run.run_id && dxRef.current !== 0) applyDx(0);
    }, [openId, run.run_id]);

    const onTouchStart = (e) => {
        const t = e.touches[0];
        touch.current = { x: t.clientX, y: t.clientY, base: dxRef.current, horizontal: null };
        setDragging(true);
    };
    const onTouchMove = (e) => {
        if (!touch.current) return;
        const t = e.touches[0];
        const ddx = t.clientX - touch.current.x;
        const ddy = t.clientY - touch.current.y;
        if (touch.current.horizontal == null && (Math.abs(ddx) > 6 || Math.abs(ddy) > 6)) {
            touch.current.horizontal = Math.abs(ddx) > Math.abs(ddy);
        }
        if (!touch.current.horizontal) return;
        applyDx(Math.min(0, Math.max(-SWIPE_OPEN - 16, touch.current.base + ddx)));
    };
    const onTouchEnd = () => {
        if (!touch.current) return;
        const wasHorizontal = touch.current.horizontal;
        touch.current = null;
        setDragging(false);
        if (!wasHorizontal) return;
        const willOpen = dxRef.current < -SWIPE_OPEN / 2;
        applyDx(willOpen ? -SWIPE_OPEN : 0);
        onOpenChange(willOpen ? run.run_id : null);
    };

    const swiped = dx !== 0;

    return (
        <div style={{ display: 'flex', gap: 14 }}>
            {/* линия + точка */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <span style={{
                    width: 12, height: 12, borderRadius: 999, marginTop: 16,
                    background: ok ? 'var(--success)' : 'var(--error)',
                    boxShadow: active ? '0 0 0 4px var(--surface-cream-strong)' : 'none', flexShrink: 0,
                }} />
                {!isLast && <span style={{ width: 2, flex: 1, background: 'var(--hairline)', marginTop: 2 }} />}
            </div>

            {/* карточка запуска + корзина за ней */}
            <div
                style={{ flex: 1, position: 'relative', marginBottom: 8 }}
                onMouseEnter={() => setHover(true)}
                onMouseLeave={() => setHover(false)}
            >
                {/* корзина монтируется только во время свайпа, иначе красный фон
                    просвечивает в скруглённых углах карточки */}
                {swiped && (
                    <button
                        onClick={() => onDelete(run.run_id)}
                        aria-label="Удалить запуск"
                        style={{
                            position: 'absolute', top: 0, bottom: 0, right: 0, width: TRASH_W,
                            border: 'none', cursor: 'pointer', background: 'var(--error)', color: '#fff',
                            borderRadius: 11,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                    >
                        <Trash2 size={16} />
                    </button>
                )}

                <button
                    onClick={() => { if (swiped) { applyDx(0); onOpenChange(null); return; } onSelect(run.run_id); }}
                    onTouchStart={onTouchStart}
                    onTouchMove={onTouchMove}
                    onTouchEnd={onTouchEnd}
                    style={{
                        width: '100%', textAlign: 'left', padding: '12px 14px', borderRadius: 11, cursor: 'pointer',
                        background: active ? 'var(--surface-cream-strong)' : 'var(--surface-card)',
                        border: `1px solid ${active ? 'var(--primary)' : 'var(--hairline)'}`,
                        boxSizing: 'border-box', position: 'relative',
                        transform: `translateX(${dx}px)`,
                        transition: dragging ? 'none' : 'transform 180ms ease',
                        touchAction: 'pan-y',
                    }}
                >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap' }}>
                        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13.5, fontWeight: 600, color: 'var(--ink)' }}>
                            {ok ? <CheckCircle size={14} style={{ color: 'var(--success)' }} /> : <AlertCircle size={14} style={{ color: 'var(--error)' }} />}
                            {relTime(run.finished_at)}
                            {run.duration_sec != null && <span style={{ color: 'var(--muted-soft)', fontWeight: 400 }}>· {fmtDuration(run.duration_sec)}</span>}
                        </span>
                        {kind === 'structured' && <HealthCounts summary={run.summary} />}
                    </div>
                    {kind === 'structured' && (
                        <div style={{ marginTop: 7 }}><DeltaBadge delta={run.delta} changed={run.changed} /></div>
                    )}
                </button>

                {/* десктоп: корзина при наведении (как в мониторинге скриптов) */}
                {hover && !swiped && (
                    <button
                        onClick={(e) => { e.stopPropagation(); onDelete(run.run_id); }}
                        title="Удалить запуск"
                        style={{
                            position: 'absolute', bottom: 8, right: 8, zIndex: 2,
                            background: 'none', border: 'none', cursor: 'pointer',
                            color: 'var(--muted-soft)', padding: 4, display: 'flex',
                            transition: 'color 120ms ease',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--error)')}
                        onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted-soft)')}
                    >
                        <Trash2 size={13} />
                    </button>
                )}
            </div>
        </div>
    );
}
TimelineRow.propTypes = {
    run: PropTypes.object.isRequired,
    kind: PropTypes.string,
    active: PropTypes.bool,
    isLast: PropTypes.bool,
    openId: PropTypes.string,
    onOpenChange: PropTypes.func.isRequired,
    onSelect: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};

export default function RunTimeline({ runsData, selectedRun, onSelect, onDelete }) {
    const [openId, setOpenId] = useState(null);
    if (!runsData) {
        return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" /> Загрузка…</div>;
    }
    const { kind, runs } = runsData;
    if (!runs.length) {
        return <div style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}>История пуста — запусков ещё не было.</div>;
    }

    return (
        <div style={{ position: 'relative', paddingLeft: 4 }}>
            {runs.map((run, i) => (
                <TimelineRow
                    key={run.run_id}
                    run={run}
                    kind={kind}
                    active={selectedRun === run.run_id || (!selectedRun && i === 0)}
                    isLast={i === runs.length - 1}
                    openId={openId}
                    onOpenChange={setOpenId}
                    onSelect={onSelect}
                    onDelete={onDelete}
                />
            ))}
        </div>
    );
}

RunTimeline.propTypes = {
    runsData: PropTypes.object,
    selectedRun: PropTypes.string,
    onSelect: PropTypes.func.isRequired,
    onDelete: PropTypes.func.isRequired,
};
