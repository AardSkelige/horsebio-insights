import { useState, useEffect, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import { m } from 'motion/react';
import { ArrowLeft, Play, Square, Loader2, CheckCircle, AlertCircle, Clock, History } from 'lucide-react';
import { checksApi, relTime, fmtDuration } from './checksShared';
import HealthResults from './HealthResults';
import ExceptionsPanel from './ExceptionsPanel';
import RunTimeline from './RunTimeline';
import ScriptLogPanel from './ScriptLogPanel';
import RunningPanel from './RunningPanel';
import InfoTip from './InfoTip';

export default function CheckDetail({ scriptId, initial, onBack }) {
    const isHealth = initial?.is_health ?? (scriptId === 'horsebio_health_check');
    const isStructured = initial?.structured ?? isHealth;
    const [tab, setTab] = useState('check'); // check | exceptions (только health)
    const [runsData, setRunsData] = useState(null);
    const [running, setRunning] = useState(initial?.is_running || false);
    const [selectedRun, setSelectedRun] = useState(null); // null = последний
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
        try { await checksApi.run(scriptId); setSelectedRun(null); setRunning(true); await loadRuns(); }
        catch (e) { alert(e.message); }
        finally { setBusy(false); }
    };
    const handleStop = async () => {
        setBusy(true);
        try { await checksApi.stop(scriptId); await loadRuns(); }
        catch (e) { alert(e.message); }
        finally { setBusy(false); }
    };
    const handleDeleteRun = async (runId) => {
        try {
            await checksApi.removeRun(scriptId, runId);
            if (selectedRun === runId) setSelectedRun(null);
            await loadRuns();
        } catch (e) { alert(e.message); }
    };

    const runs = runsData?.runs || [];
    const latest = runs[0];

    // Основная панель: при запуске — живой лог; иначе результат/лог выбранного запуска
    let main;
    if (running) {
        main = <RunningPanel scriptId={scriptId} onFinished={loadRuns} />;
    } else if (isStructured) {
        main = <HealthResults scriptId={scriptId} runId={selectedRun} running={false} />;
    } else {
        main = <ScriptLogPanel scriptId={scriptId} runId={selectedRun} />;
    }

    return (
        <div style={{ maxWidth: 1200, margin: '0 auto' }}>
            <button onClick={onBack} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: 'var(--muted)', fontSize: 13, fontWeight: 600, cursor: 'pointer', marginBottom: 14, padding: 0 }}>
                <ArrowLeft size={16} /> Все проверки
            </button>

            {/* Шапка */}
            <div style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 14, padding: 18, marginBottom: 18, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
                <div>
                    <div style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 600, color: 'var(--ink)' }}>{initial?.name || scriptId}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginTop: 6, fontSize: 13, color: 'var(--muted)', flexWrap: 'wrap' }}>
                        <StatusBadge running={running} latest={latest} />
                        {latest && (
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                                <Clock size={13} /> {relTime(latest.finished_at)}{latest.duration_sec != null && ` · ${fmtDuration(latest.duration_sec)}`}
                            </span>
                        )}
                        <span style={{ color: 'var(--muted-soft)' }}>{initial?.schedule}</span>
                    </div>
                </div>
                {running ? (
                    <button onClick={handleStop} disabled={busy} style={btnStyle('var(--error)')}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Square size={15} />} Остановить</button>
                ) : (
                    <button onClick={handleRun} disabled={busy} style={btnStyle('var(--primary)')}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />} Запустить</button>
                )}
            </div>

            {/* Переключатель только у health: Проверка / Исключения */}
            {isHealth && (
                <div style={{ display: 'inline-flex', gap: 4, padding: 4, background: 'var(--surface-soft)', borderRadius: 10, marginBottom: 18 }}>
                    <Seg active={tab === 'check'} onClick={() => setTab('check')}>Проверка</Seg>
                    <Seg active={tab === 'exceptions'} onClick={() => setTab('exceptions')}>Исключения</Seg>
                </div>
            )}

            {isHealth && tab === 'exceptions' ? (
                <ExceptionsPanel />
            ) : (
                <div className="checks-detail-grid">
                    <div style={{ minWidth: 0 }}>{main}</div>
                    <aside>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 12 }}>
                            <History size={14} /> История
                            <InfoTip text="Точки — счётчики находок по уровням (критичные / важные / предупреждения). Стрелка ↓ зелёным = находок стало меньше к прошлому запуску, ↑ = больше." />
                        </div>
                        <RunTimeline
                            runsData={runsData}
                            selectedRun={selectedRun}
                            onSelect={(runId) => { setSelectedRun(runId); setTab('check'); }}
                            onDelete={handleDeleteRun}
                        />
                    </aside>
                </div>
            )}
        </div>
    );
}

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

function StatusBadge({ running, latest }) {
    if (running) return <span style={{ color: 'var(--primary)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 5 }}><Loader2 size={14} className="animate-spin" /> Выполняется</span>;
    if (!latest) return <span style={{ color: 'var(--muted-soft)' }}>Не запускался</span>;
    if (latest.exit_code === 0 || latest.exit_code == null) return <span style={{ color: 'var(--success)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 5 }}><CheckCircle size={14} /> Успешно</span>;
    return <span style={{ color: 'var(--error)', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: 5 }}><AlertCircle size={14} /> Ошибка</span>;
}
StatusBadge.propTypes = { running: PropTypes.bool, latest: PropTypes.object };

function btnStyle(color) {
    return { display: 'inline-flex', alignItems: 'center', gap: 7, padding: '9px 18px', borderRadius: 10, background: color, color: '#fff', border: 'none', fontSize: 14, fontWeight: 600, cursor: 'pointer' };
}

CheckDetail.propTypes = {
    scriptId: PropTypes.string.isRequired,
    initial: PropTypes.object,
    onBack: PropTypes.func.isRequired,
};
