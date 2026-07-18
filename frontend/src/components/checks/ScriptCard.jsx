import PropTypes from 'prop-types';
import { Loader2, CheckCircle, AlertCircle, Circle, ChevronRight, Clock } from 'lucide-react';
import { SEV, sevOf, relTime, plural } from './checksShared';

// Подписи severity с русским склонением
const SEV_WORDS = {
    critical:  ['критичная', 'критичные', 'критичных'],
    important: ['важная', 'важные', 'важных'],
    warning:   ['предупреждение', 'предупреждения', 'предупреждений'],
};

function SeverityChip({ sev, count }) {
    const c = SEV[sev];
    const w = SEV_WORDS[sev];
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            padding: '2px 9px', borderRadius: 999, fontSize: 12, fontWeight: 600,
            color: c.color, background: c.bg, whiteSpace: 'nowrap',
        }}>
            <span style={{ width: 7, height: 7, borderRadius: 999, background: c.color }} />
            {count} {w ? plural(count, ...w) : ''}
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
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
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

/** Мини-сводка внутренних проверок хелс-чека: проблемные поимённо, чистые одним счётчиком.
 *  Отвечает на вопрос «что именно проверяется и где проблемы» прямо в списке. */
function HealthChecksStrip({ checks }) {
    const problems = checks.filter((c) => c.status === 'problems');
    const clean = checks.filter((c) => c.status === 'ok').length;
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 9 }}>
            {problems.map((c) => {
                const s = sevOf(c.severity);
                return (
                    <span key={c.id} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5, padding: '2px 9px',
                        borderRadius: 999, fontSize: 12, fontWeight: 600, color: s.color, background: s.bg,
                    }}>
                        <span style={{ width: 6, height: 6, borderRadius: 999, background: s.color }} />
                        {c.title} · {c.count}
                    </span>
                );
            })}
            {clean > 0 && (
                <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--success)' }}>
                    ✓ {problems.length ? 'остальные ' : ''}{clean} {plural(clean, 'проверка чистая', 'проверки чистые', 'проверок чистые')}
                </span>
            )}
        </div>
    );
}
HealthChecksStrip.propTypes = { checks: PropTypes.array.isRequired };

/** Строка-плашка скрипта на всю ширину: название и суть слева, статус и время справа. */
export default function ScriptCard({ script, onOpen }) {
    const healthChecks = script.is_health && Array.isArray(script.summary?.checks)
        ? script.summary.checks : null;
    return (
        <div
            role="button"
            tabIndex={0}
            onClick={() => onOpen(script.id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onOpen(script.id); }}
            className="group"
            style={{
                width: '100%', textAlign: 'left',
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: 12, padding: '13px 16px', cursor: 'pointer',
                transition: 'background 0.15s, border-color 0.15s',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--surface-cream-strong)'; e.currentTarget.style.borderColor = 'var(--primary)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'var(--surface-card)'; e.currentTarget.style.borderColor = 'var(--hairline)'; }}
        >
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>{script.name}</div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 2, lineHeight: 1.4 }}>{script.description}</div>
                </div>
                <StatusLine script={script} />
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: 'var(--muted-soft)', whiteSpace: 'nowrap', flexShrink: 0 }}>
                    <Clock size={12} />
                    {script.last_run ? relTime(script.last_run.finished_at) : script.schedule}
                </span>
                <ChevronRight size={17} style={{ color: 'var(--muted-soft)', flexShrink: 0 }} />
            </div>
            {healthChecks && <HealthChecksStrip checks={healthChecks} />}
        </div>
    );
}

ScriptCard.propTypes = {
    script: PropTypes.object.isRequired,
    onOpen: PropTypes.func.isRequired,
};
