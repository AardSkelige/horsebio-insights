import { useState, useRef, useEffect } from 'react';
import PropTypes from 'prop-types';
import { Download, FileSpreadsheet, Megaphone, ShoppingCart, PercentCircle, X } from 'lucide-react';
import { Button, IconButton, Input, Notice as UiNotice } from '../../ui';
import { generateReport, exportAdvertisingData, exportSalesData } from '../api/ozonApi';


const noticeShape = PropTypes.shape({ type: PropTypes.string.isRequired, text: PropTypes.string.isRequired });

const Notice = ({ notice }) => notice
    ? <UiNotice tone={notice.type}>{notice.text}</UiNotice>
    : null;

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
            <IconButton icon={X} label="Убрать файл" size={12} onClick={onClear} />
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
                style={{ border: `1px dashed ${dragOver ? 'var(--primary)' : 'var(--hairline)'}`, borderRadius: '8px', padding: '18px 12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer', backgroundColor: dragOver ? 'var(--accent-wash)' : 'transparent', transition: 'border-color 150ms, background-color 150ms', userSelect: 'none' }}
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
                    <Input type="date" value={adsStart} onChange={e => setAdsStart(e.target.value)} style={{ flex: 1, height: 36 }} />
                    <Input type="date" value={adsEnd} onChange={e => setAdsEnd(e.target.value)} style={{ flex: 1, height: 36 }} />
                </div>
                <Button variant="primary" icon={Download} disabled={!adsStart || !adsEnd} onClick={handleExportAds}>
                    Скачать Excel
                </Button>
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
                    <Input type="date" value={salesStart} onChange={e => setSalesStart(e.target.value)} style={{ flex: 1, height: 36 }} />
                    <Input type="date" value={salesEnd} onChange={e => setSalesEnd(e.target.value)} style={{ flex: 1, height: 36 }} />
                </div>
                <Button variant="primary" icon={Download} disabled={!salesStart || !salesEnd} onClick={handleExportSales}>
                    Скачать Excel
                </Button>
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

                <Button
                    variant="primary"
                    loading={loading}
                    disabled={!adsFile || !productsFile}
                    onClick={handleGenerateReport}
                    style={{ height: 42 }}
                >
                    {loading ? 'Генерация...' : 'Сгенерировать отчёт ДРР'}
                </Button>
                {notices.drr && <Notice notice={notices.drr} />}
            </section>
        </div>
    );
};

export default ReportSection;
