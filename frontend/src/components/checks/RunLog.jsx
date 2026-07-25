import { useMemo, useRef, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Copy, Check, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react';

/*
 * Журнал выполнения задания — человекочитаемое представление вывода прогона.
 * Бэкенд (sync/logger.py) печатает строки вида «\033[NNm[HH:MM:SS] сообщение\033[0m»,
 * где ANSI-цвет кодирует уровень. Здесь цвет → семантический уровень, а строки
 * рендерятся аккуратными рядами (без терминала/моноширинного вывода и ANSI-мусора).
 */

const LEVEL_BY_CODE = {
    33: 'warning', 31: 'error', 37: 'debug',
    32: 'success', 36: 'section', 35: 'progress', 34: 'stats',
};
// eslint-disable-next-line no-control-regex
const ANSI_ALL = /\x1b\[[0-9;]*m/g;
// eslint-disable-next-line no-control-regex
const ANSI_FIRST = /\x1b\[([0-9;]*)m/;

function levelOf(line) {
    const m = line.match(ANSI_FIRST);
    if (!m) return 'info';
    for (const c of m[1].split(';').filter(Boolean).map(Number)) {
        if (LEVEL_BY_CODE[c]) return LEVEL_BY_CODE[c];
    }
    return 'info';
}

/** Разбор сырого лога прогона в структурированные записи. */
function parseRun(content) {
    const lines = (content || '').replace(/\r/g, '').split('\n');
    const out = [];
    let lastTime = null;
    for (const rawLine of lines) {
        const level = levelOf(rawLine);
        let text = rawLine.replace(ANSI_ALL, '');

        let time = null;
        const tm = text.match(/^\s*\[(\d{2}:\d{2}:\d{2})\]\s?([\s\S]*)$/);
        if (tm) { time = tm[1]; text = tm[2]; }

        const trimmed = text.trim();
        if (trimmed === '') continue;                       // пустые строки
        if (/^[=_]{3,}$/.test(trimmed) || /^-{4,}$/.test(trimmed)) continue; // разделители

        let indent = 0;
        const im = text.match(/^( +)/);
        if (im) { indent = Math.min(4, Math.round(im[1].length / 2)); text = text.replace(/^ +/, ''); }

        const showTime = Boolean(time) && time !== lastTime;
        if (time) lastTime = time;

        out.push({ time, showTime, level, text, indent });
    }
    return out;
}

const LEVEL_ICON = {
    success: CheckCircle2,
    warning: AlertTriangle,
    error: XCircle,
};

export default function RunLog({ content, title = 'Журнал выполнения', maxHeight = '60vh', autoScroll = false }) {
    const [copied, setCopied] = useState(false);
    const bodyRef = useRef(null);
    const entries = useMemo(() => parseRun(content), [content]);

    useEffect(() => {
        if (autoScroll && bodyRef.current) {
            bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
        }
    }, [content, autoScroll]);

    const copy = () => {
        const plain = (content || '').replace(ANSI_ALL, '');
        navigator.clipboard?.writeText(plain).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1600);
        }).catch(() => {});
    };

    return (
        <div className="runlog">
            <div className="runlog__head">
                <span className="runlog__title">{title}</span>
                <button className="runlog__copy" onClick={copy} type="button">
                    {copied ? <Check size={12} /> : <Copy size={12} />}
                    <span>{copied ? 'Скопировано' : 'Копировать'}</span>
                </button>
            </div>
            <div className="runlog__body" ref={bodyRef} style={{ maxHeight }}>
                {entries.map((e, i) => {
                    if (e.level === 'section') {
                        return (
                            <div className="runlog__section" key={i}>
                                <span className="runlog__section-label">{e.text}</span>
                            </div>
                        );
                    }
                    const Icon = LEVEL_ICON[e.level];
                    return (
                        <div className={`runlog__row runlog__row--${e.level}`} key={i}>
                            <span className="runlog__time">{e.showTime ? e.time : ''}</span>
                            <span className="runlog__msg" style={e.indent ? { paddingLeft: e.indent * 14 } : undefined}>
                                {Icon && <Icon size={13} className="runlog__ic" />}
                                <span>{e.text}</span>
                            </span>
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

RunLog.propTypes = {
    content: PropTypes.string,
    title: PropTypes.string,
    maxHeight: PropTypes.oneOfType([PropTypes.string, PropTypes.number]),
    autoScroll: PropTypes.bool,
};
