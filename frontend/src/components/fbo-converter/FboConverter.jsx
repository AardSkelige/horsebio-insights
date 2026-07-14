import { useState, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { FileSpreadsheet, ArrowRight, X, Upload, CheckCircle, AlertCircle, AlertTriangle } from 'lucide-react';
import { convertFboSupply } from './api/fboConverterApi';
import SectionLabel from '../ui/SectionLabel';

/* ── Shared primitives (same pattern as FBOAnalysis / ProductionCalculator) ── */


const btnStyle = (primary, disabled = false) => ({
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '6px 16px', borderRadius: '8px', border: 'none',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
    transition: 'background-color 150ms ease',
});

/* ── Notice ────────────────────────────────────────────────── */

const NOTICE_ICON  = { success: CheckCircle, error: AlertCircle, warning: AlertTriangle };
const NOTICE_COLOR = {
    success: { border: 'var(--primary)', text: 'var(--primary)', bg: 'var(--surface-soft)' },
    error:   { border: '#c64545',        text: '#c64545',        bg: 'var(--surface-soft)' },
    warning: { border: '#d4a017',        text: '#d4a017',        bg: 'var(--surface-soft)' },
};

const Notice = ({ type, text, onClose }) => {
    const c    = NOTICE_COLOR[type] || NOTICE_COLOR.warning;
    const Icon = NOTICE_ICON[type]  || AlertTriangle;
    return (
        <div style={{
            display: 'flex', alignItems: 'flex-start', gap: 10,
            padding: '10px 14px', borderRadius: 8,
            background: c.bg, border: `1px solid ${c.border}`,
        }}>
            <Icon size={14} style={{ color: c.text, flexShrink: 0, marginTop: 2 }} />
            <span style={{ flex: 1, fontSize: 13, color: 'var(--body)' }}>{text}</span>
            {onClose && (
                <button onClick={onClose}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--muted)' }}>
                    <X size={14} />
                </button>
            )}
        </div>
    );
};

Notice.propTypes = {
    type: PropTypes.string.isRequired,
    text: PropTypes.string.isRequired,
    onClose: PropTypes.func,
};

/* ── DropZone ──────────────────────────────────────────────── */

const DropZone = ({ file, onFile, onClear }) => {
    const inputRef = useRef(null);
    const [dragging, setDragging] = useState(false);

    const pick = (f) => { if (f && f.name.endsWith('.xlsx')) onFile(f); };

    const onDrop = useCallback((e) => {
        e.preventDefault();
        setDragging(false);
        pick(e.dataTransfer.files[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [onFile]);

    if (file) {
        return (
            <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                padding: '10px 14px', borderRadius: 8,
                border: '1px solid var(--hairline)', background: 'var(--surface-soft)',
            }}>
                <FileSpreadsheet size={16} style={{ color: 'var(--primary)', flexShrink: 0 }} />
                <span style={{
                    flex: 1, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)',
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                    {file.name}
                </span>
                <button onClick={onClear}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: 'var(--muted)' }}>
                    <X size={13} />
                </button>
            </div>
        );
    }

    return (
        <div
            onDrop={onDrop}
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onClick={() => inputRef.current?.click()}
            style={{
                border: `2px dashed ${dragging ? 'var(--primary)' : 'var(--hairline)'}`,
                borderRadius: 8, padding: '32px 16px', textAlign: 'center', cursor: 'pointer',
                background: dragging ? 'var(--surface-card)' : 'var(--surface-soft)',
                transition: 'border-color 0.15s, background 0.15s',
            }}
        >
            <input ref={inputRef} type="file" accept=".xlsx" style={{ display: 'none' }}
                onChange={e => pick(e.target.files[0])} />
            <Upload size={24} style={{
                color: dragging ? 'var(--primary)' : 'var(--muted)',
                margin: '0 auto 10px', display: 'block', transition: 'color 0.15s',
            }} />
            <div style={{ fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
                Excel-файл с прогнозом
            </div>
            <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
                Нажмите или перетащите .xlsx файл
            </div>
        </div>
    );
};

DropZone.propTypes = {
    file: PropTypes.instanceOf(File),
    onFile: PropTypes.func.isRequired,
    onClear: PropTypes.func.isRequired,
};

/* ── Main ──────────────────────────────────────────────────── */

const FboConverter = () => {
    const [file, setFile]     = useState(null);
    const [loading, setLoading] = useState(false);
    const [notice, setNotice] = useState(null);

    const showNotice = (type, text) => {
        setNotice({ type, text });
        if (type === 'success') setTimeout(() => setNotice(null), 4000);
    };

    const handleConvert = async () => {
        if (!file) { showNotice('warning', 'Загрузите Excel-файл с прогнозом для конвертации'); return; }
        try {
            setLoading(true);
            setNotice(null);
            await convertFboSupply(file);
            setFile(null);
            showNotice('success', 'Файл FBO-поставки сформирован и скачивается');
        } catch (error) {
            const msg = error.response?.data?.message || error.message || 'Неизвестная ошибка';
            showNotice('error', `Ошибка конвертации: ${msg}`);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', color: 'var(--ink)' }}>

            {/* PageHeader */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                    <h1 style={{
                        fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400,
                        letterSpacing: '-0.025em', lineHeight: 1.1,
                        color: 'var(--ink)', margin: 0, marginBottom: '4px',
                    }}>
                        FBO Конвертер
                    </h1>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                        Конвертация прогноза в Excel-шаблон для создания FBO-поставки на Ozon
                    </p>
                </div>
                <button
                    onClick={handleConvert}
                    disabled={loading || !file}
                    style={btnStyle(true, loading || !file)}
                >
                    <FileSpreadsheet size={13} />
                    {loading ? 'Конвертируем…' : 'Конвертировать'}
                </button>
            </div>

            {/* Инструкция */}
            <section>
                <SectionLabel>Как работает конвертер</SectionLabel>
                <div style={{
                    padding: '16px 18px', borderRadius: 12,
                    background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
                        <code style={{
                            fontFamily: 'var(--mono)', fontSize: 12,
                            background: 'var(--surface-cream-strong)', color: 'var(--body)',
                            padding: '4px 10px', borderRadius: 6,
                        }}>
                            Артикул · SKU · Количество
                        </code>
                        <ArrowRight size={13} style={{ color: 'var(--muted)', flexShrink: 0 }} />
                        <code style={{
                            fontFamily: 'var(--mono)', fontSize: 12,
                            background: 'var(--surface-cream-strong)', color: 'var(--body)',
                            padding: '4px 10px', borderRadius: 6,
                        }}>
                            FBO-шаблон Ozon
                        </code>
                    </div>
                    <ul style={{ margin: 0, paddingLeft: 16, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--body)', lineHeight: 1.8 }}>
                        <li>Загружаем название, штрихкод, Ozon ID по артикулу</li>
                        <li>Определяем ликвидность и зону размещения по SKU</li>
                        <li>Результат — готовый шаблон для загрузки в Ozon Seller Portal</li>
                    </ul>
                </div>
            </section>

            {/* Загрузка файла */}
            <section>
                <SectionLabel>Входной файл</SectionLabel>
                <p style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', margin: '0 0 10px' }}>
                    Любой лист, колонки: <b>Артикул</b>, <b>SKU</b> (числовой Ozon ID), <b>Количество</b>
                </p>
                <DropZone file={file} onFile={setFile} onClear={() => setFile(null)} />
            </section>

            {/* Уведомление */}
            {notice && (
                <Notice type={notice.type} text={notice.text} onClose={() => setNotice(null)} />
            )}
        </div>
    );
};

export default FboConverter;
