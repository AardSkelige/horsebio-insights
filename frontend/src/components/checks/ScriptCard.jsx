import PropTypes from 'prop-types';
import { Loader2, CheckCircle, AlertCircle, Circle, ChevronRight, Clock } from 'lucide-react';
import { SEV, relTime } from './checksShared';

function SeverityChip({ sev, count }) {
    const c = SEV[sev];
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '2px 9px', borderRadius: 999, fontSize: 12, fontWeight: 600,
            color: c.color, background: c.bg,
        }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color }} />
            {count}
        </span>
    );
}
SeverityChip.propTypes = { sev: PropTypes.string, count: PropTypes.number };

function StatusLine({ script }) {
    if (script.is_running) {
        return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--primary)', fontSize: 13, fontWeight: 600 }}>
                <Loader2 size={14} className="animate-spin" /> Выполняется…
            </span>
        );
    }
    if (script.structured && script.summary) {
        const s = script.summary;
        const total = (s.critical || 0) + (s.important || 0) + (s.warnings || 0);
        if (total === 0) {
            return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, fontWeight: 600 }}><CheckCircle size={14} /> ОК</span>;
        }
        return (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {s.critical ? <SeverityChip sev="critical" count={s.critical} /> : null}
                {s.important ? <SeverityChip sev="important" count={s.important} /> : null}
                {s.warnings ? <SeverityChip sev="warning" count={s.warnings} /> : null}
            </div>
        );
    }
    const code = script.last_run?.exit_code;
    if (code == null) {
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--muted-soft)', fontSize: 13 }}><Circle size={13} /> Не запускался</span>;
    }
    if (code === 0) {
        return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--success)', fontSize: 13, fontWeight: 600 }}><CheckCircle size={14} /> ОК</span>;
    }
    return <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'var(--error)', fontSize: 13, fontWeight: 600 }}><AlertCircle size={14} /> Ошибка</span>;
}
StatusLine.propTypes = { script: PropTypes.object.isRequired };

export default function ScriptCard({ script, onOpen }) {
    return (
        <button
            onClick={() => onOpen(script.id)}
            className="group"
            style={{
                textAlign: 'left', width: '100%',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: 14, padding: 16, cursor: 'pointer',
                display: 'flex', flexDirection: 'column', gap: 12,
                transition: 'background 0.15s, border-color 0.15s, transform 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-cream-strong)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface-card)'; e.currentTarget.style.borderColor = 'var(--hairline)'; }}
        >
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>{script.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2 }}>{script.description}</div>
                </div>
                <ChevronRight size={18} style={{ color: 'var(--muted-soft)', flexShrink: 0, marginTop: 2 }} />
            </div>

            <StatusLine script={script} />

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 'auto', paddingTop: 4 }}>
                <span style={{
                    fontSize: 11, fontWeight: 600, color: 'var(--muted)',
                    padding: '2px 8px', borderRadius: 6, background: 'var(--surface-soft)',
                }}>{script.account}</span>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--muted-soft)' }}>
                    <Clock size={12} />
                    {script.last_run ? relTime(script.last_run.finished_at) : script.schedule}
                </span>
            </div>
        </button>
    );
}

ScriptCard.propTypes = {
    script: PropTypes.object.isRequired,
    onOpen: PropTypes.func.isRequired,
};
