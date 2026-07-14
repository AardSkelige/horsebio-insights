import { useState, useRef, useEffect } from 'react';
import { FileSpreadsheet, Boxes, Palette, Warehouse, Truck, X, Loader2 } from 'lucide-react';
import { processStockAvailability } from '../api/ozonApi';

const btn = (primary, disabled = false) => ({
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
    width: '100%', height: '42px', borderRadius: '8px', border: 'none',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
    transition: 'background-color 150ms ease',
});

const StockAvailabilitySection = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [notice, setNotice] = useState(null);
    const inputRef = useRef(null);

    useEffect(() => {
        if (!notice || notice.type === 'loading') return;
        const t = setTimeout(() => setNotice(null), 3000);
        return () => clearTimeout(t);
    }, [notice]);

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) setFile(f);
    };

    const handleProcessFile = async () => {
        if (!file) { setNotice({ type: 'warning', text: 'Необходимо загрузить файл для обработки' }); return; }
        setLoading(true);
        setNotice({ type: 'loading', text: 'Обработка файла...' });
        try {
            await processStockAvailability(file);
            setFile(null);
            setNotice({ type: 'success', text: 'Файл с результатами скачивается' });
        } catch (error) {
            setNotice({ type: 'error', text: error.message || 'Ошибка обработки файла' });
        } finally {
            setLoading(false);
        }
    };

    const noticeColors = { error: '#c64545', success: '#059669', warning: '#d4a017', loading: 'var(--muted)' };
    const noticeBgs = { error: 'rgba(198,69,69,0.08)', success: 'rgba(5,150,105,0.08)', warning: 'rgba(212,160,23,0.08)', loading: 'var(--surface-card)' };

    return (
        <div className="ozon-compact-flow">
            <div className="ozon-metric-list">
                <div><Warehouse size={16} /> Остатки по регионам</div>
                <div><Palette size={16} /> Индикация запасов</div>
                <div><Boxes size={16} /> Итоги по складам</div>
                <div><Truck size={16} /> Товары в пути</div>
            </div>

            <input ref={inputRef} type="file" accept=".xlsx" onChange={e => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ''; }} style={{ display: 'none' }} />

            {file ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', border: '1px solid var(--hairline)', borderRadius: '8px', backgroundColor: 'var(--surface-card)' }}>
                    <FileSpreadsheet style={{ width: 14, height: 14, color: 'var(--primary)', flexShrink: 0 }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
                    <button onClick={() => setFile(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--muted)', display: 'flex', flexShrink: 0 }}>
                        <X style={{ width: 12, height: 12 }} />
                    </button>
                </div>
            ) : (
                <div
                    onClick={() => inputRef.current?.click()}
                    onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    style={{ border: `1px dashed ${dragOver ? 'var(--primary)' : 'var(--hairline)'}`, borderRadius: '8px', padding: '20px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer', backgroundColor: dragOver ? 'rgba(204,120,92,0.04)' : 'transparent', transition: 'border-color 150ms, background-color 150ms', userSelect: 'none' }}
                >
                    <FileSpreadsheet style={{ width: 22, height: 22, color: dragOver ? 'var(--primary)' : 'var(--muted)' }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>Файл доступности товаров</span>
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' }}>XLSX отчёт OZON</span>
                </div>
            )}

            <button onClick={handleProcessFile} disabled={loading || !file} style={btn(true, loading || !file)}>
                {loading ? <><Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />Обработка...</> : 'Обработать файл'}
            </button>

            {notice && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '9px 12px', borderRadius: '8px', border: `1px solid ${noticeColors[notice.type]}40`, backgroundColor: noticeBgs[notice.type], fontFamily: 'var(--sans)', fontSize: '12px', color: noticeColors[notice.type] }}>
                    {notice.type === 'loading' && <Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />}
                    {notice.text}
                </div>
            )}
        </div>
    );
};

export default StockAvailabilitySection;
