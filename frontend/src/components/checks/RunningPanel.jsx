import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Loader2, ChevronRight } from 'lucide-react';
import { checksApi } from './checksShared';

function lastMeaningfulLine(content) {
    if (!content) return '';
    const lines = content.split('\n').map((l) => l.trim())
        .filter((l) => l && !/^[=─\-_]{5,}$/.test(l));
    return lines.length ? lines[lines.length - 1] : '';
}

export default function RunningPanel({ scriptId, onFinished }) {
    const [content, setContent] = useState('');
    const [showLog, setShowLog] = useState(false);
    const pollRef = useRef(null);

    const load = useCallback(async () => {
        try {
            const res = await checksApi.log(scriptId);
            setContent(res.content || '');
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

    const status = lastMeaningfulLine(content);

    return (
        <div>
            <div style={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 14, padding: '24px 26px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, color: 'var(--primary)', fontWeight: 600, fontSize: 14.5 }}>
                    <Loader2 size={17} className="animate-spin" /> Проверка выполняется…
                </div>
                <div className="checks-progress" style={{ marginBottom: status ? 18 : 0 }} />
                {status && (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                        <span style={{ fontSize: 12, color: 'var(--muted-soft)', flexShrink: 0 }}>Сейчас</span>
                        <span style={{ fontSize: 13, color: 'var(--body)' }}>{status}</span>
                    </div>
                )}
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
