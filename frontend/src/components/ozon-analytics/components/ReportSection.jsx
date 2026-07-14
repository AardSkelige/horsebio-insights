import { useState, useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Download, FileSpreadsheet, Megaphone, ShoppingCart, PercentCircle, X, Loader2 } from 'lucide-react';
import { generateReport, exportAdvertisingData, exportSalesData } from '../api/ozonApi';

const btn = (primary, disabled = false) => ({
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
    width: '100%', height: '40px', borderRadius: '8px', border: 'none',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1,
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
    transition: 'background-color 150ms ease',
});

const dateInputStyle = {
    flex: 1, height: '36px', padding: '0 10px',
    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
    backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)',
    borderRadius: '8px', outline: 'none', transition: 'border-color 150ms',
};

const noticeShape = PropTypes.shape({ type: PropTypes.string.isRequired, text: PropTypes.string.isRequired });

const Notice = ({ notice }) => {
    if (!notice) return null;
    const colors = { error: '#c64545', success: '#059669', warning: '#d4a017' };
    const bgs = { error: 'rgba(198,69,69,0.08)', success: 'rgba(5,150,105,0.08)', warning: 'rgba(212,160,23,0.08)' };
    return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '9px 12px', borderRadius: '8px', border: `1px solid ${colors[notice.type]}40`, backgroundColor: bgs[notice.type], fontFamily: 'var(--sans)', fontSize: '12px', color: colors[notice.type] }}>
            {notice.type === 'loading' ? <Loader2 style={{ width: 13, height: 13 }} className="animate-spin" /> : null}
            {notice.text}
        </div>
    );
};

Notice.propTypes = { notice: noticeShape };

const UploadZone = ({ file, onFile, onClear, accept, label }) => {
    const inputRef = useRef(null);
    const [dragOver, setDragOver] = useState(false);

    const handleDrop = (e) => {
        e.preventDefault(); setDragOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
    };

    if (file) return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 12px', border: '1px solid var(--hairline)', borderRadius: '8px', backgroundColor: 'var(--surface-card)' }}>
            <FileSpreadsheet style={{ width: 14, height: 14, color: 'var(--primary)', flexShrink: 0 }} />
            <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</span>
            <button onClick={onClear} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '2px', color: 'var(--muted)', display: 'flex', flexShrink: 0 }}>
                <X style={{ width: 12, height: 12 }} />
            </button>
        </div>
    );

    return (
        <>
            <input ref={inputRef} type="file" accept={accept} onChange={e => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ''; }} style={{ display: 'none' }} />
            <div
                onClick={() => inputRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                style={{ border: `1px dashed ${dragOver ? 'var(--primary)' : 'var(--hairline)'}`, borderRadius: '8px', padding: '18px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer', backgroundColor: dragOver ? 'rgba(204,120,92,0.04)' : 'transparent', transition: 'border-color 150ms, background-color 150ms', userSelect: 'none' }}
            >
                <FileSpreadsheet style={{ width: 20, height: 20, color: dragOver ? 'var(--primary)' : 'var(--muted)' }} />
                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', fontWeight: 500, color: 'var(--ink)' }}>{label}</span>
                <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', color: 'var(--muted)' }}>{accept.toUpperCase().replace(/\./g, '').replace(/,/g, ', ')}</span>
            </div>
        </>
    );
};

UploadZone.propTypes = {
    file: PropTypes.instanceOf(File),
    onFile: PropTypes.func.isRequired,
    onClear: PropTypes.func.isRequired,
    accept: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
};

const ReportSection = () => {
    const [adsFile, setAdsFile] = useState(null);
    const [productsFile, setProductsFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [adsStart, setAdsStart] = useState('');
    const [adsEnd, setAdsEnd] = useState('');
    const [salesStart, setSalesStart] = useState('');
    const [salesEnd, setSalesEnd] = useState('');
    const [notices, setNotices] = useState({ ads: null, sales: null, drr: null });

    const showNotice = (key, type, text) => setNotices(prev => ({ ...prev, [key]: { type, text } }));

    useEffect(() => {
        Object.keys(notices).forEach(key => {
            if (notices[key] && notices[key].type !== 'loading') {
                const t = setTimeout(() => setNotices(prev => ({ ...prev, [key]: null })), 3000);
                return () => clearTimeout(t);
            }
        });
    }, [notices]);

    const handleExportAds = () => {
        if (!adsStart || !adsEnd) { showNotice('ads', 'warning', 'Выберите начальную и конечную дату'); return; }
        exportAdvertisingData(adsStart, adsEnd);
    };

    const handleExportSales = () => {
        if (!salesStart || !salesEnd) { showNotice('sales', 'warning', 'Выберите начальную и конечную дату'); return; }
        exportSalesData(salesStart, salesEnd);
    };

    const handleGenerateReport = async () => {
        if (!adsFile || !productsFile) { showNotice('drr', 'warning', 'Загрузите оба файла'); return; }
        setLoading(true);
        showNotice('drr', 'loading', 'Генерация отчёта...');
        try {
            await generateReport(adsFile, productsFile);
            setAdsFile(null); setProductsFile(null);
            showNotice('drr', 'success', 'Отчёт сгенерирован');
        } catch (error) {
            showNotice('drr', 'error', error.message || 'Ошибка генерации отчёта');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="ozon-report-grid">
            <section className="ozon-section ozon-action-card">
                <div className="ozon-section__heading">
                    <div className="ozon-section__icon"><Megaphone size={18} /></div>
                    <div>
                        <h2>Выгрузка рекламы</h2>
                        <p>Excel-файл с рекламными данными за выбранный период.</p>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input type="date" value={adsStart} onChange={e => setAdsStart(e.target.value)} style={dateInputStyle}
                        onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                    <input type="date" value={adsEnd} onChange={e => setAdsEnd(e.target.value)} style={dateInputStyle}
                        onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                </div>
                <button onClick={handleExportAds} disabled={!adsStart || !adsEnd} style={btn(true, !adsStart || !adsEnd)}>
                    <Download size={14} /> Скачать Excel
                </button>
                {notices.ads && <Notice notice={notices.ads} />}
            </section>

            <section className="ozon-section ozon-action-card">
                <div className="ozon-section__heading">
                    <div className="ozon-section__icon"><ShoppingCart size={18} /></div>
                    <div>
                        <h2>Выгрузка продаж</h2>
                        <p>Excel-файл с продажами и товарными показателями за период.</p>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <input type="date" value={salesStart} onChange={e => setSalesStart(e.target.value)} style={dateInputStyle}
                        onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                    <input type="date" value={salesEnd} onChange={e => setSalesEnd(e.target.value)} style={dateInputStyle}
                        onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                        onBlur={e => e.target.style.borderColor = 'var(--hairline)'} />
                </div>
                <button onClick={handleExportSales} disabled={!salesStart || !salesEnd} style={btn(true, !salesStart || !salesEnd)}>
                    <Download size={14} /> Скачать Excel
                </button>
                {notices.sales && <Notice notice={notices.sales} />}
            </section>

            <section className="ozon-section ozon-drr-card">
                <div className="ozon-section__heading">
                    <div className="ozon-section__icon"><PercentCircle size={18} /></div>
                    <div>
                        <h2>ДРР отчет</h2>
                        <p>Загрузите два файла из кабинета OZON и сформируйте итоговый Excel.</p>
                    </div>
                </div>

                <div className="ozon-metric-list ozon-drr-files">
                    <div><FileSpreadsheet size={16} /> SKU Statistics: рекламная статистика</div>
                    <div><FileSpreadsheet size={16} /> Analytics Report: товары и продажи</div>
                </div>

                <div className="ozon-drr-upload-grid">
                    <div>
                        <p className="ozon-upload-title">1. SKU Statistics</p>
                        <UploadZone file={adsFile} onFile={setAdsFile} onClear={() => setAdsFile(null)} accept=".csv,.xlsx,.xls" label="sku_statistics_*.xlsx" />
                    </div>
                    <div>
                        <p className="ozon-upload-title">2. Analytics Report</p>
                        <UploadZone file={productsFile} onFile={setProductsFile} onClear={() => setProductsFile(null)} accept=".xlsx" label="analytics_report_*.xlsx" />
                    </div>
                </div>

                <button onClick={handleGenerateReport} disabled={loading || !adsFile || !productsFile} style={{ ...btn(true, loading || !adsFile || !productsFile), height: '42px' }}>
                    {loading ? <><Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />Генерация...</> : 'Сгенерировать отчёт ДРР'}
                </button>
                {notices.drr && <Notice notice={notices.drr} />}
            </section>
        </div>
    );
};

export default ReportSection;
