import { useState, useEffect, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { Loader2 } from 'lucide-react';
import { checksApi } from './checksShared';

// Маркеры severity в начале строки → цвет
const MARKERS = [
    [/^(\s*)(🔴|❌)\s?/u, '#c64545'],
    [/^(\s*)(🟠)\s?/u, '#c47d2f'],
    [/^(\s*)(🟡|⚠️|⚠)\s?/u, '#b08a1f'],
    [/^(\s*)(🟢|✅|✓)\s?/u, '#5db872'],
];

function classify(line) {
    const t = line.trim();
    if (!t) return { type: 'blank' };
    if (/^[=─\-_]{5,}\s*$/.test(t)) return { type: 'rule' };
    // Заголовок секции: ВЕРХНИЙ РЕГИСТР, без ведущего эмодзи
    if (/^[A-ZА-ЯЁ0-9 ()«»"'\-—.:№%]{6,}$/u.test(t) && t.length < 70 && /[A-ZА-ЯЁ]/u.test(t)) {
        return { type: 'header', text: t };
    }
    for (const [re, color] of MARKERS) {
        if (re.test(line)) {
            const indent = line.match(/^\s*/)[0].length;
            return { type: 'sev', color, text: line.replace(re, '$1').trimStart(), nested: indent > 2 };
        }
    }
    return { type: 'line', text: line };
}

function Report({ content }) {
    if (!content) return <span style={{ color: 'var(--muted-soft)', fontStyle: 'italic' }}>Пусто</span>;
    const lines = content.split('\n');
    const out = [];
    lines.forEach((line, i) => {
        const c = classify(line);
        if (c.type === 'blank') { out.push(<div key={i} style={{ height: '0.5em' }} />); return; }
        if (c.type === 'rule') { out.push(<div key={i} style={{ borderTop: '1px solid var(--hairline-soft)', margin: '6px 0' }} />); return; }
        if (c.type === 'header') {
            out.push(
                <div key={i} style={{
                    fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 700, letterSpacing: 0.4,
                    textTransform: 'uppercase', color: 'var(--ink)', marginTop: 16, marginBottom: 6,
                }}>{c.text}</div>
            );
            return;
        }
        if (c.type === 'sev') {
            out.push(
                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline', paddingLeft: c.nested ? 16 : 0, marginTop: c.nested ? 0 : 4 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color, flexShrink: 0, transform: 'translateY(-1px)' }} />
                    <span style={{ color: c.color, fontWeight: c.nested ? 400 : 600 }}>{c.text}</span>
                </div>
            );
            return;
        }
        out.push(<div key={i} style={{ color: 'var(--body)' }}>{line || '​'}</div>);
    });
    return <>{out}</>;
}
Report.propTypes = { content: PropTypes.string };

export default function ScriptLogPanel({ scriptId, runId, running }) {
    const [data, setData] = useState(undefined);
    const pollRef = useRef(null);

    const load = useCallback(async () => {
        try { const res = await checksApi.log(scriptId, runId); setData(res); return res.is_running; }
        catch { setData({ content: '', is_running: false }); return false; }
    }, [scriptId, runId]);

    useEffect(() => { load(); }, [load]);

    useEffect(() => {
        const shouldPoll = running || data?.is_running;
        if (shouldPoll && !pollRef.current) {
            pollRef.current = setInterval(async () => {
                const still = await load();
                if (!still) { clearInterval(pollRef.current); pollRef.current = null; }
            }, 2500);
        }
        return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
    }, [running, data?.is_running, load]);

    if (data === undefined) {
        return <div style={{ display: 'flex', gap: 8, color: 'var(--muted)', padding: 30, justifyContent: 'center' }}><Loader2 size={18} className="animate-spin" /> Загрузка…</div>;
    }

    const isRunning = running || data.is_running;
    return (
        <div>
            {isRunning && (
                <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 7, fontSize: 12.5, color: 'var(--primary)', marginBottom: 8, fontWeight: 600 }}>
                        <Loader2 size={14} className="animate-spin" /> Выполняется…
                    </div>
                    <div className="checks-progress" />
                </div>
            )}
            <div style={{
                background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: 12,
                padding: '18px 22px', fontFamily: 'var(--mono)', fontSize: 12.5, lineHeight: 1.65,
                whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: '70vh', overflowY: 'auto',
            }}>
                <Report content={data.content} />
            </div>
        </div>
    );
}

ScriptLogPanel.propTypes = {
    scriptId: PropTypes.string.isRequired,
    runId: PropTypes.string,
    running: PropTypes.bool,
};
