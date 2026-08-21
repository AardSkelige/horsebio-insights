import { useState, useEffect, useCallback, useRef } from 'react';
import PropTypes from 'prop-types';
import { ArrowLeft, Play, Square, Loader2, Activity } from 'lucide-react';
import { Button, Segmented } from '../ui';
import { checksApi, relTime, fmtDuration, plural, SEV } from './checksShared';
import { SCRIPT_META, AccountBadge } from './ScriptCard';
import HealthResults from './HealthResults';
import LogResult from './LogResult';
import ExceptionsPanel from './ExceptionsPanel';
import RunningPanel from './RunningPanel';
import InfoTip from './InfoTip';
import './CheckDetail.css';

export default function CheckDetail({ scriptId, initial, onBack, backLabel = 'Все проверки' }) {
    const isHealth = initial?.is_health ?? (scriptId === 'horsebio_health_check');
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

    // Основная панель: при запуске — живой лог; иначе структурированный результат.
    // Пока не пришёл initial (заход по прямой ссылке, список ещё не загружен) —
    // ждём данные вместо преждевременного рендера.
    let main;
    if (running) {
        main = <RunningPanel scriptId={scriptId} onFinished={loadRuns} />;
    } else if (!initial) {
        main = (
            <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}>
                <Loader2 size={18} className="animate-spin" /> Загрузка…
            </div>
        );
    } else if (initial.structured === false) {
        // «Лог»-задания (синхронизация, инвентаризация) не дают структурированных
        // находок — показываем вывод последнего запуска, а не пустой экран находок.
        main = <LogResult scriptId={scriptId} />;
    } else {
        // onExceptionChange → перечитать runs: заголовок «● N проблема» берёт summary
        // из последнего запуска, а бэкенд пересчитывает его с учётом исключений
        main = <HealthResults scriptId={scriptId} runId={null} running={false} onExceptionChange={loadRuns} />;
    }

    return (
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
            <Button variant="quiet" icon={ArrowLeft} onClick={onBack} style={{ marginBottom: 16 }}>
                {backLabel}
            </Button>

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
                    <Button variant="danger" icon={Square} loading={busy} onClick={handleStop}>Остановить</Button>
                ) : (
                    <Button variant="primary" icon={Play} loading={busy} onClick={handleRun}>Запустить</Button>
                )}
            </div>

            {/* Переключатель только у health: Проверка / Исключения */}
            {isHealth && (
                <Segmented
                    layoutId="check-detail-tab"
                    value={tab}
                    onChange={setTab}
                    options={[
                        { value: 'check', label: 'Проверка' },
                        { value: 'exceptions', label: 'Исключения' },
                    ]}
                    className="check-detail__tabs"
                />
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
    // Цвет по severity — как во внешней карточке (важное → оранжевый, а не всегда красный)
    const sevColor = SEV[s.critical ? 'critical' : s.important ? 'important' : 'warning'].color;
    return (
        <span style={{ display: 'inline-flex', gap: 14, flexWrap: 'wrap' }}>
            {failed ? (
                <span style={{ color: 'var(--error)', fontWeight: 700 }}>● запуск с ошибкой</span>
            ) : problems > 0 ? (
                <span style={{ color: sevColor, fontWeight: 700 }}>● {problems} {plural(problems, 'проблема', 'проблемы', 'проблем')}</span>
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



CheckDetail.propTypes = {
    scriptId: PropTypes.string.isRequired,
    initial: PropTypes.object,
    onBack: PropTypes.func.isRequired,
    backLabel: PropTypes.string,
};
