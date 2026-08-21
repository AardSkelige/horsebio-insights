import { useState, useRef, useCallback } from 'react';
import PropTypes from 'prop-types';
import { FileSpreadsheet, ArrowRight, X, Upload } from 'lucide-react';
import { convertFboSupply } from './api/fboConverterApi';
import { Button, IconButton, Notice, Page, PageHeader, SectionLabel } from '../ui';

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
                <IconButton icon={X} label="Убрать файл" size={13} onClick={onClear} />
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
        <Page>
            <PageHeader
                title="FBO Конвертер"
                subtitle="Конвертация прогноза в Excel-шаблон для создания FBO-поставки на Ozon"
                actions={
                    <Button
                        variant="primary"
                        icon={FileSpreadsheet}
                        loading={loading}
                        disabled={!file}
                        onClick={handleConvert}
                    >
                        {loading ? 'Конвертируем…' : 'Конвертировать'}
                    </Button>
                }
            />

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
                <Notice tone={notice.type} onClose={() => setNotice(null)}>{notice.text}</Notice>
            )}
        </Page>
    );
};

export default FboConverter;
