import { useState, useRef, useEffect } from 'react';
import { FileSpreadsheet, Boxes, Palette, Warehouse, Truck, X } from 'lucide-react';
import { Button, Notice } from '../../ui';
import { processStockAvailability } from '../api/ozonApi';


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
                    style={{ border: `1px dashed ${dragOver ? 'var(--primary)' : 'var(--hairline)'}`, borderRadius: '8px', padding: '20px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer', backgroundColor: dragOver ? 'var(--accent-wash)' : 'transparent', transition: 'border-color 150ms, background-color 150ms', userSelect: 'none' }}
                >
                    <FileSpreadsheet style={{ width: 22, height: 22, color: dragOver ? 'var(--primary)' : 'var(--muted)' }} />
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>Файл доступности товаров</span>
                    <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' }}>XLSX отчёт OZON</span>
                </div>
            )}

            <Button variant="primary" loading={loading} disabled={!file} onClick={handleProcessFile}>
                {loading ? 'Обработка...' : 'Обработать файл'}
            </Button>

            {notice && <Notice tone={notice.type}>{notice.text}</Notice>}
        </div>
    );
};

export default StockAvailabilitySection;
