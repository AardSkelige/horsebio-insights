import { useState, useEffect, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import { m } from 'motion/react';
import { ArrowLeft, Play, Square, Loader2, Activity } from 'lucide-react';
import { checksApi, relTime, fmtDuration, plural } from './checksShared';
import { SCRIPT_META, AccountBadge } from './ScriptCard';
import HealthResults from './HealthResults';
import ExceptionsPanel from './ExceptionsPanel';
import ScriptLogPanel from './ScriptLogPanel';
import RunningPanel from './RunningPanel';
import InfoTip from './InfoTip';
import './CheckDetail.css';

export default function CheckDetail({ scriptId, initial, onBack }) {
    const isHealth = initial?.is_health ?? (scriptId === 'horsebio_health_check');
    const isStructured = initial?.structured ?? isHealth;
    const [tab, setTab] = useState('check'); // check | exceptions (только health)
    const [runsData, setRunsData] = useState(null);
    const [running, setRunning] = useState(initial?.is_running || false);
    const [busy, setBusy] = useState(false);
    const pollRef = useRef(null);

    const loadRuns = useCallback(async () => {
        try {
            const res = await checksApi.runs(scriptId);
            setRunsData(res);
            setRunning(res.is_running);
            return res.is_running;
        } catch { return false; }
    }, [scriptId]);

    useEffect(() => { loadRuns(); }, [loadRuns]);

    useEffect(() => {
        if (running && !pollRef.current) {
            pollRef.current = setInterval(async () => {
                const still = await loadRuns();
                if (!still) { clearInterval(pollRef.current); pollRef.current = null; }
            }, 3000);
        }
        return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
    }, [running, loadRuns]);

    const handleRun = async () => {
        setBusy(true);
        try { await checksApi.run(scriptId); setRunning(true); await loadRuns(); }
        catch (e) { alert(e.message); }
        finally { setBusy(false); }
    };
    const handleStop = async () => {
        setBusy(true);
        try { await checksApi.stop(scriptId); await loadRuns(); }
        catch (e) { alert(e.message); }
        finally { setBusy(false); }
    };

    const runs = runsData?.runs || [];
    const latest = runs[0];
    const meta = SCRIPT_META[scriptId] || {};
    const Icon = meta.Icon || Activity;

    // Основная панель: при запуске — живой лог; иначе последний результат/лог
    let main;
    if (running) {
        main = <RunningPanel scriptId={scriptId} onFinished={loadRuns} />;
    } else if (isStructured) {
        main = <HealthResults scriptId={scriptId} runId={null} running={false} />;
    } else {
        main = <ScriptLogPanel scriptId={scriptId} runId={null} />;
    }

    return (
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: 'var(--muted)', fontSize: 13, fontWeight: 600, cursor: 'pointer', marginBottom: 16, padding: 0 }}>
                <ArrowLeft size={16} /> Все проверки
            </button>

            {/* Шапка — та же строка, что на главной странице проверок */}
            <div className="check-detail__header">
                <div className="check-detail__title-group">
                    <Icon size={20} style={{ color: 'var(--muted)', flexShrink: 0, marginTop: 4 }} />
                    <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 9, flexWrap: 'wrap', fontFamily: 'var(--serif)', fontSize: 24, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.15 }}>
                            {initial?.name || scriptId}
                            {initial?.account && <AccountBadge account={initial.account} />}
                            {meta.hint && <InfoTip text={meta.hint} width={310} />}
                        </div>
                        {meta.what && (
                            <div style={{ fontSize: 12.5, color: 'var(--muted)', marginTop: 5, lineHeight: 1.5 }}>
                                <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Что проверяем:</b> {meta.what}</div>
                                <div><b style={{ color: 'var(--body)', fontWeight: 600 }}>Как:</b> {meta.how}</div>
                            </div>
                        )}
                        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: 'var(--muted-soft)', marginTop: 6 }}>
                            <RunSummary running={running} latest={latest} />
                            {initial?.schedule && <span>{initial.schedule.toLowerCase()}</span>}
                        </div>
                    </div>
                </div>
                {running ? (
                    <button className="check-detail__run-btn" onClick={handleStop} disabled={busy} style={btnStyle('var(--error)')}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Square size={15} />} Остановить</button>
                ) : (
                    <button className="check-detail__run-btn" onClick={handleRun} disabled={busy} style={btnStyle('var(--primary)')}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />} Запустить</button>
                )}
            </div>

            {/* Переключатель только у health: Проверка / Исключения */}
            {isHealth && (
                <div style={{ display: 'inline-flex', gap: 4, padding: 4, background: 'var(--surface-soft)', borderRadius: 10, marginBottom: 18 }}>
                    <Seg active={tab === 'check'} onClick={() => setTab('check')}>Проверка</Seg>
                    <Seg active={tab === 'exceptions'} onClick={() => setTab('exceptions')}>Исключения</Seg>
                </div>
            )}

            {isHealth && tab === 'exceptions' ? <ExceptionsPanel /> : main}
        </div>
    );
}

/** Статус и время последнего запуска одной строкой: «● 3 проблемы · сегодня 09:00 · 13с» */
function RunSummary({ running, latest }) {
    if (running) {
        return <span style={{ color: 'var(--primary)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 5 }}><Loader2 size={13} className="animate-spin" /> Выполняется…</span>;
    }
    if (!latest) return <span>Не запускался</span>;
    const s = latest.summary || {};
    const problems = (s.critical || 0) + (s.important || 0) + (s.warnings || 0);
    const failed = latest.exit_code != null && latest.exit_code !== 0;
    return (
        <span style={{ display: 'inline-flex', gap: 14, flexWrap: 'wrap' }}>
            {failed ? (
                <span style={{ color: 'var(--error)', fontWeight: 700 }}>● запуск с ошибкой</span>
            ) : problems > 0 ? (
                <span style={{ color: 'var(--error)', fontWeight: 700 }}>● {problems} {plural(problems, 'проблема', 'проблемы', 'проблем')}</span>
            ) : (
                <span style={{ color: 'var(--success)', fontWeight: 700 }}>✓ всё чисто</span>
            )}
            <span>
                запуск {relTime(latest.finished_at)}
                {latest.duration_sec != null && ` · ${fmtDuration(latest.duration_sec)}`}
            </span>
        </span>
    );
}
RunSummary.propTypes = { running: PropTypes.bool, latest: PropTypes.object };

function Seg({ active, onClick, children }) {
    return (
        <button onClick={onClick} style={{
            position: 'relative',
            padding: '6px 16px', fontSize: 13, fontWeight: 600, cursor: 'pointer', borderRadius: 7, border: 'none',
            background: 'transparent', color: active ? 'var(--ink)' : 'var(--muted)',
            transition: 'color 150ms ease',
        }}>
            {active && (
                <m.span
                    layoutId="checks-seg-pill"
                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                    style={{ position: 'absolute', inset: 0, borderRadius: 7, background: 'var(--canvas)', boxShadow: '0 1px 2px rgba(0,0,0,0.06)' }}
                />
            )}
            <span style={{ position: 'relative' }}>{children}</span>
        </button>
    );
}
Seg.propTypes = { active: PropTypes.bool, onClick: PropTypes.func, children: PropTypes.node };

function btnStyle(color) {
    return { display: 'inline-flex', alignItems: 'center', gap: 7, padding: '9px 18px', borderRadius: 10, background: color, color: '#fff', border: 'none', fontSize: 14, fontWeight: 600, cursor: 'pointer', flexShrink: 0 };
}

CheckDetail.propTypes = {
    scriptId: PropTypes.string.isRequired,
    initial: PropTypes.object,
    onBack: PropTypes.func.isRequired,
};
