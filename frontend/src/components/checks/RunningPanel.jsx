import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Loader2, ChevronRight } from 'lucide-react';
import { checksApi } from './checksShared';

const ellipsis = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' };

export default function RunningPanel({ scriptId, onFinished }) {
    const [content, setContent] = useState('');
    const [progress, setProgress] = useState(null);
    const [showLog, setShowLog] = useState(false);
    const pollRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const res = await checksApi.log(scriptId);
            setContent(res.content || '');
            setProgress(res.progress || null);
            return res.is_running;
        } catch { return true; }
    }, [scriptId]);

    useEffect(() => {
        let stop = false;
        const tick = async () => {
            const running = await load();
            if (!running && !stop) { onFinished?.(); }
        };
        tick();
        pollRef.current = setInterval(tick, 2000);
        return () => { stop = true; if (pollRef.current) clearInterval(pollRef.current); };
    }, [load, onFinished]);

    const step = progress?.step;
    const item = progress?.item;

    return (
        <div>
            <div style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 14, padding: '20px 22px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: step || item ? 14 : 0, color: 'var(--primary)', fontWeight: 600, fontSize: 14.5 }}>
                    <Loader2 size={17} className="animate-spin" /> Проверка выполняется…
                </div>

                {step && (
                    <div style={{ marginBottom: item ? 12 : 0 }}>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 6 }}>
                            {step.total != null && (
                                <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--muted)', flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                                    {step.n}/{step.total}
                                </span>
                            )}
                            <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--ink)', ...ellipsis }}>
                                {step.title}
                            </span>
                        </div>
                        {step.total != null && (
                            <div
                                className="checks-progress checks-progress--determinate"
                                style={{ '--checks-progress-pct': `${(step.n / step.total) * 100}%` }}
                            />
                        )}
                    </div>
                )}

                {item && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12.5, color: 'var(--muted)' }}>
                        <span style={{ flexShrink: 0, fontVariantNumeric: 'tabular-nums' }}>
                            {item.total != null ? `${item.i}/${item.total}` : `#${item.i}`}
                        </span>
                        <span style={ellipsis}>{item.name}</span>
                    </div>
                )}

                {!step && !item && <div className="checks-progress" />}
            </div>

            <button onClick={() => setShowLog((v) => !v)} style={{
                display: 'inline-flex', alignItems: 'center', gap: 5, marginTop: 12, padding: 0,
                background: 'none', border: 'none', color: 'var(--muted)', fontSize: 12.5, fontWeight: 600, cursor: 'pointer',
            }}>
                <ChevronRight size={14} style={{ transform: showLog ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
                {showLog ? 'Скрыть вывод' : 'Показать вывод'}
            </button>

            {showLog && (
                <div style={{
                    marginTop: 10, background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 10,
                    padding: '12px 14px', fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.55, color: 'var(--muted)',
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '40vh', overflowY: 'auto',
                }}>{content || 'Ожидание вывода…'}</div>
            )}
        </div>
    );
}

RunningPanel.propTypes = {
    scriptId: PropTypes.string.isRequired,
    onFinished: PropTypes.func,
};
