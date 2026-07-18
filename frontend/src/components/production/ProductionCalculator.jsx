import { useState, useCallback, useRef, useEffect, Fragment } from 'react';
import PropTypes from 'prop-types';
import { Factory, Search, Trash2, Calculator, Download, Loader2, ChevronDown, ChevronUp, FileSpreadsheet } from 'lucide-react';
import { m } from 'motion/react';
import SectionLabel from '../ui/SectionLabel';
import { FadeRise } from '../ui/motion';
import { productionApi } from '../../api/productionApi';

const useDebounce = (callback, delay) => {
    const timeoutRef = useRef(null);
    useEffect(() => () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); }, []);
    return useCallback((...args) => {
        if (timeoutRef.current) clearTimeout(timeoutRef.current);
        timeoutRef.current = setTimeout(() => callback(...args), delay);
    }, [callback, delay]);
};

const btn = (primary, disabled = false) => ({
    display: 'inline-flex', alignItems: 'center', gap: '6px',
    padding: '6px 14px', borderRadius: '8px', border: 'none',
    fontFamily: 'var(--sans)', fontSize: '13px', fontWeight: 500,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.6 : 1,
    backgroundColor: primary ? 'var(--primary)' : 'var(--surface-card)',
    color: primary ? '#fff' : 'var(--ink)',
    transition: 'background-color 150ms ease',
});

const thStyle = {
    padding: '8px 12px',
    fontFamily: 'var(--sans)',
    fontSize: '11px',
    fontWeight: 500,
    letterSpacing: '0.07em',
    textTransform: 'uppercase',
    color: 'var(--muted)',
    textAlign: 'left',
    borderBottom: '1px solid var(--hairline)',
    backgroundColor: 'var(--canvas)',
    whiteSpace: 'nowrap',
};

const Badge = ({ text, color, bg }) => (
    <span style={{ fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500, color, backgroundColor: bg, borderRadius: '9999px', padding: '2px 8px', whiteSpace: 'nowrap' }}>
        {text}
    </span>
);

Badge.propTypes = { text: PropTypes.string.isRequired, color: PropTypes.string.isRequired, bg: PropTypes.string.isRequired };

const TechCardBadge = ({ has }) => has
    ? <Badge text="Есть" color="#059669" bg="rgba(5,150,105,0.1)" />
    : <Badge text="Нет" color="#d4a017" bg="rgba(212,160,23,0.1)" />;

TechCardBadge.propTypes = { has: PropTypes.bool };

const StatusBadge = ({ record }) => {
    if (record.has_processing_plan) return <Badge text="Рассчитан" color="#059669" bg="rgba(5,150,105,0.1)" />;
    if (record.found) return <Badge text="Нет техкарты" color="#d4a017" bg="rgba(212,160,23,0.1)" />;
    return <Badge text="Не найден" color="#dc2626" bg="rgba(220,38,38,0.1)" />;
};

StatusBadge.propTypes = { record: PropTypes.shape({ has_processing_plan: PropTypes.bool, found: PropTypes.bool }).isRequired };

const ProductionCalculator = () => {
    const [activeTab, setActiveTab] = useState('manual');
    const [manualItems, setManualItems] = useState([]);
    const [searchResults, setSearchResults] = useState([]);
    const [searchLoading, setSearchLoading] = useState(false);
    const [searchValue, setSearchValue] = useState('');
    const [showDropdown, setShowDropdown] = useState(false);
    const [calculating, setCalculating] = useState(false);
    const [exporting, setExporting] = useState(false);
    const [result, setResult] = useState(null);
    const [expandedRows, setExpandedRows] = useState(new Set());
    const [dragOver, setDragOver] = useState(false);
    const [notice, setNotice] = useState(null);
    const fileInputRef = useRef(null);
    const searchContainerRef = useRef(null);

    useEffect(() => {
        if (!notice || notice.type === 'loading') return;
        const t = setTimeout(() => setNotice(null), 3000);
        return () => clearTimeout(t);
    }, [notice]);

    useEffect(() => {
        const handler = (e) => {
            if (searchContainerRef.current && !searchContainerRef.current.contains(e.target))
                setShowDropdown(false);
        };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const showNotice = (type, text) => setNotice({ type, text });

    const doSearch = useCallback(async (query) => {
        if (!query || query.length < 2) { setSearchResults([]); setShowDropdown(false); return; }
        setSearchLoading(true);
        try {
            const data = await productionApi.searchProducts(query);
            if (data.success) {
                setSearchResults(data.products);
                setShowDropdown(data.products.length > 0);
            }
        } catch (err) {
            console.error('Search error:', err);
        } finally {
            setSearchLoading(false);
        }
    }, []);

    const searchProducts = useDebounce(doSearch, 300);

    const handleAddProduct = (product) => {
        if (manualItems.some(item => item.article === product.article)) {
            showNotice('warning', 'Этот товар уже добавлен');
            return;
        }
        setManualItems(prev => [...prev, { article: product.article, name: product.name, quantity: 1, has_processing_plan: product.has_processing_plan }]);
        setSearchValue('');
        setSearchResults([]);
        setShowDropdown(false);
    };

    const handleQuantityChange = (article, quantity) => {
        setManualItems(items => items.map(item => item.article === article ? { ...item, quantity: Number(quantity) || 0 } : item));
    };

    const handleRemoveProduct = (article) => {
        setManualItems(items => items.filter(item => item.article !== article));
    };

    const processFile = async (file) => {
        const formData = new FormData();
        formData.append('file', file);
        setCalculating(true);
        showNotice('loading', 'Обработка файла...');
        try {
            const data = await productionApi.calculateFromFile(file);
            if (data.success !== false) {
                setResult(data);
                showNotice('success', 'Расчёт завершён!');
            } else {
                showNotice('error', data.error || data.message || 'Ошибка обработки файла');
            }
        } catch (err) {
            console.error('Upload error:', err);
            showNotice('error', 'Ошибка загрузки файла');
        } finally {
            setCalculating(false);
        }
    };

    const handleFileInputChange = (e) => {
        const file = e.target.files?.[0];
        if (file) processFile(file);
        e.target.value = '';
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file && (file.name.endsWith('.xlsx') || file.name.endsWith('.xls'))) processFile(file);
    };

    const handleCalculateManual = async () => {
        if (manualItems.length === 0) { showNotice('warning', 'Добавьте товары для расчёта'); return; }
        const validItems = manualItems.filter(item => item.quantity > 0);
        if (validItems.length === 0) { showNotice('warning', 'Укажите количество для товаров'); return; }
        setCalculating(true);
        showNotice('loading', 'Расчёт компонентов...');
        try {
            const data = await productionApi.calculateFromItems(
                validItems.map(item => ({ article: item.article, quantity: item.quantity }))
            );
            if (data.success !== false) {
                setResult(data);
                showNotice('success', 'Расчёт завершён!');
            } else {
                showNotice('error', data.error || data.message || 'Ошибка расчёта');
            }
        } catch (err) {
            console.error('Calculate error:', err);
            showNotice('error', 'Ошибка расчёта');
        } finally {
            setCalculating(false);
        }
    };

    const handleExport = async () => {
        if (!result) return;
        setExporting(true);
        showNotice('loading', 'Формируется файл...');
        try {
            const blob = await productionApi.export(result);
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            const date = new Date().toLocaleDateString('ru-RU').replace(/\./g, '');
            link.href = url;
            link.download = `production_components_${date}.xlsx`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            showNotice('success', 'Файл скачан');
        } catch (err) {
            console.error('Export error:', err);
            showNotice('error', 'Ошибка экспорта');
        } finally {
            setExporting(false);
        }
    };

    const handleClear = () => { setResult(null); setManualItems([]); setExpandedRows(new Set()); };

    const toggleExpanded = (article) => setExpandedRows(prev => {
        const next = new Set(prev);
        next.has(article) ? next.delete(article) : next.add(article);
        return next;
    });

    const noticeColors = { error: '#dc2626', success: '#059669', warning: '#d4a017', loading: 'var(--surface-dark)' };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', color: 'var(--ink)' }}>

            {/* Header */}
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '12px' }}>
                <div>
                    <h1 style={{ fontFamily: 'var(--serif)', fontSize: '32px', fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: 0, marginBottom: '4px' }}>
                        Расчёт компонентов производства
                    </h1>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>
                        Материалы для производства товаров по техкартам
                    </p>
                </div>
                {result && (
                    <div style={{ display: 'flex', gap: '8px', flexShrink: 0 }}>
                        <button onClick={handleClear} style={btn(false)}>Очистить всё</button>
                        <button onClick={handleExport} disabled={exporting} style={btn(true, exporting)}>
                            {exporting
                                ? <><Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />Экспорт...</>
                                : <><Download style={{ width: 13, height: 13 }} />Экспорт</>
                            }
                        </button>
                    </div>
                )}
            </div>

            {/* Input section */}
            <section>
                <SectionLabel>Ввод данных</SectionLabel>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid var(--hairline)', marginBottom: '20px' }}>
                    {[{ key: 'manual', label: 'Ручной ввод' }, { key: 'upload', label: 'Загрузить Excel' }].map(tab => (
                        <button
                            key={tab.key}
                            onClick={() => setActiveTab(tab.key)}
                            style={{
                                position: 'relative',
                                padding: '8px 16px', border: 'none', cursor: 'pointer',
                                fontFamily: 'var(--sans)', fontSize: '13px',
                                fontWeight: activeTab === tab.key ? 500 : 400,
                                backgroundColor: 'transparent',
                                color: activeTab === tab.key ? 'var(--ink)' : 'var(--muted)',
                                marginBottom: '-1px',
                                transition: 'color 150ms',
                            }}
                        >
                            {tab.label}
                            {activeTab === tab.key && (
                                <m.span
                                    layoutId="production-tabs-underline"
                                    transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                                    style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: 2, background: 'var(--primary)' }}
                                />
                            )}
                        </button>
                    ))}
                </div>

                {/* Manual input */}
                {activeTab === 'manual' && (
                    <FadeRise style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                        <div ref={searchContainerRef} style={{ position: 'relative' }}>
                            <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', width: 14, height: 14, color: 'var(--muted)', pointerEvents: 'none' }} />
                            <input
                                value={searchValue}
                                onChange={(e) => { setSearchValue(e.target.value); searchProducts(e.target.value); }}
                                placeholder="Поиск по артикулу или названию..."
                                style={{
                                    width: '100%', boxSizing: 'border-box',
                                    padding: '9px 36px 9px 36px',
                                    fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)',
                                    backgroundColor: 'var(--canvas)',
                                    border: '1px solid var(--hairline)', borderRadius: '8px', outline: 'none',
                                    transition: 'border-color 150ms',
                                }}
                                onFocus={(e) => { e.target.style.borderColor = 'var(--primary)'; if (searchResults.length > 0) setShowDropdown(true); }}
                                onBlur={(e) => { e.target.style.borderColor = 'var(--hairline)'; }}
                            />
                            {searchLoading && <Loader2 style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', width: 14, height: 14, color: 'var(--muted)' }} className="animate-spin" />}

                            {showDropdown && searchResults.length > 0 && (
                                <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 50, backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '8px', marginTop: '4px', boxShadow: '0 4px 12px rgba(20,20,19,0.12)', overflow: 'hidden' }}>
                                    {searchResults.map(product => (
                                        <div
                                            key={product.article}
                                            onMouseDown={() => handleAddProduct(product)}
                                            style={{ padding: '10px 14px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', borderBottom: '1px solid var(--hairline)', transition: 'background-color 100ms' }}
                                            onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-card)'}
                                            onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                        >
                                            <div style={{ overflow: 'hidden', flex: 1, display: 'flex', gap: '8px', alignItems: 'baseline', minWidth: 0 }}>
                                                <span style={{ fontFamily: 'var(--mono)', fontSize: '12px', fontWeight: 500, color: 'var(--ink)', flexShrink: 0 }}>{product.article}</span>
                                                <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{product.name}</span>
                                            </div>
                                            <TechCardBadge has={product.has_processing_plan} />
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {manualItems.length > 0 ? (
                            <>
                                <div style={{ overflowX: 'auto' }}>
                                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr>
                                                <th style={{ ...thStyle, width: 120 }}>Артикул</th>
                                                <th style={thStyle}>Наименование</th>
                                                <th style={{ ...thStyle, width: 100 }}>Техкарта</th>
                                                <th style={{ ...thStyle, width: 120, textAlign: 'right' }}>Количество</th>
                                                <th style={{ ...thStyle, width: 48 }}></th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {manualItems.map(item => (
                                                <tr key={item.article} style={{ borderBottom: '1px solid var(--hairline)' }}
                                                    onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-card)'}
                                                    onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                                >
                                                    <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted)' }}>{item.article}</td>
                                                    <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>{item.name}</td>
                                                    <td style={{ padding: '9px 12px' }}><TechCardBadge has={item.has_processing_plan} /></td>
                                                    <td style={{ padding: '9px 12px', textAlign: 'right' }}>
                                                        <input
                                                            type="number"
                                                            min={1}
                                                            value={item.quantity}
                                                            onChange={e => handleQuantityChange(item.article, e.target.value)}
                                                            style={{ width: '80px', textAlign: 'right', padding: '5px 8px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', backgroundColor: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: '6px', outline: 'none' }}
                                                            onFocus={e => e.target.style.borderColor = 'var(--primary)'}
                                                            onBlur={e => e.target.style.borderColor = 'var(--hairline)'}
                                                        />
                                                    </td>
                                                    <td style={{ padding: '9px 12px', textAlign: 'right' }}>
                                                        <button
                                                            onClick={() => handleRemoveProduct(item.article)}
                                                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '4px', color: 'var(--muted)', display: 'flex', alignItems: 'center', transition: 'color 150ms' }}
                                                            onMouseEnter={e => e.currentTarget.style.color = '#dc2626'}
                                                            onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}
                                                        >
                                                            <Trash2 style={{ width: 14, height: 14 }} />
                                                        </button>
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                                    <button onClick={handleCalculateManual} disabled={calculating} style={btn(true, calculating)}>
                                        {calculating
                                            ? <><Loader2 style={{ width: 13, height: 13 }} className="animate-spin" />Расчёт...</>
                                            : <><Calculator style={{ width: 13, height: 13 }} />Рассчитать компоненты</>
                                        }
                                    </button>
                                </div>
                            </>
                        ) : (
                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '48px 0', gap: '8px' }}>
                                <Factory style={{ width: 32, height: 32, color: 'var(--hairline)' }} />
                                <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>Добавьте товары для расчёта</p>
                            </div>
                        )}
                    </FadeRise>
                )}

                {/* File upload */}
                {activeTab === 'upload' && (
                    <FadeRise>
                        <input ref={fileInputRef} type="file" accept=".xlsx,.xls" onChange={handleFileInputChange} style={{ display: 'none' }} />
                        <div
                            onClick={() => !calculating && fileInputRef.current?.click()}
                            onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                            onDragLeave={() => setDragOver(false)}
                            onDrop={handleDrop}
                            style={{
                                border: `2px dashed ${dragOver ? 'var(--primary)' : 'var(--hairline)'}`,
                                borderRadius: '12px', padding: '48px 24px',
                                display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px',
                                cursor: calculating ? 'default' : 'pointer',
                                backgroundColor: dragOver ? 'rgba(204,120,92,0.04)' : 'transparent',
                                transition: 'border-color 150ms, background-color 150ms',
                                userSelect: 'none',
                            }}
                        >
                            {calculating
                                ? <Loader2 style={{ width: 32, height: 32, color: 'var(--primary)' }} className="animate-spin" />
                                : <FileSpreadsheet style={{ width: 32, height: 32, color: dragOver ? 'var(--primary)' : 'var(--muted)' }} />
                            }
                            <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--ink)', margin: 0 }}>
                                {calculating ? 'Обработка файла...' : 'Перетащите Excel файл или нажмите для выбора'}
                            </p>
                            <p style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)', margin: 0, textAlign: 'center' }}>
                                Файл должен содержать колонки: Артикул, Наименование, Количество
                            </p>
                        </div>
                    </FadeRise>
                )}
            </section>

            {/* Results */}
            {result && (
                <>
                    {result.components_summary?.length > 0 && (
                        <section>
                            <SectionLabel>Сводка компонентов ({result.components_summary.length})</SectionLabel>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr>
                                            <th style={{ ...thStyle, width: 40 }}>№</th>
                                            <th style={thStyle}>Материал</th>
                                            <th style={{ ...thStyle, width: 80 }}>Ед.изм.</th>
                                            <th style={{ ...thStyle, width: 140, textAlign: 'right' }}>Количество</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {result.components_summary.map((c, i) => (
                                            <tr key={c.material_id} style={{ borderBottom: '1px solid var(--hairline)' }}
                                                onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-card)'}
                                                onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                            >
                                                <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted-soft)' }}>{i + 1}</td>
                                                <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>{c.material_name}</td>
                                                <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted)' }}>{c.uom}</td>
                                                <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>
                                                    {c.total_quantity?.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )}

                    {result.products?.length > 0 && (
                        <section>
                            <SectionLabel>
                                Детали по товарам ({result.products_found} найдено{result.products_not_found > 0 && `, ${result.products_not_found} не найдено`}{result.products_without_processing_plan > 0 && `, ${result.products_without_processing_plan} без техкарт`})
                            </SectionLabel>
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr>
                                            <th style={{ ...thStyle, width: 32 }}></th>
                                            <th style={{ ...thStyle, width: 120 }}>Артикул</th>
                                            <th style={thStyle}>Наименование</th>
                                            <th style={{ ...thStyle, width: 80, textAlign: 'right' }}>Кол-во</th>
                                            <th style={{ ...thStyle, width: 130 }}>Статус</th>
                                            <th style={thStyle}>Техкарта</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {result.products.map(p => {
                                            const canExpand = p.has_processing_plan && p.components?.length > 0;
                                            const isExpanded = expandedRows.has(p.article);
                                            return (
                                                <Fragment key={p.article}>
                                                    <tr
                                                        style={{ borderBottom: '1px solid var(--hairline)', cursor: canExpand ? 'pointer' : 'default' }}
                                                        onClick={() => canExpand && toggleExpanded(p.article)}
                                                        onMouseEnter={e => e.currentTarget.style.backgroundColor = 'var(--surface-card)'}
                                                        onMouseLeave={e => e.currentTarget.style.backgroundColor = 'transparent'}
                                                    >
                                                        <td style={{ padding: '9px 12px', width: 32 }}>
                                                            {canExpand && (isExpanded
                                                                ? <ChevronUp style={{ width: 14, height: 14, color: 'var(--muted)' }} />
                                                                : <ChevronDown style={{ width: 14, height: 14, color: 'var(--muted)' }} />
                                                            )}
                                                        </td>
                                                        <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--muted)' }}>{p.article}</td>
                                                        <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--ink)' }}>{p.name}</td>
                                                        <td style={{ padding: '9px 12px', fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', textAlign: 'right' }}>{p.quantity}</td>
                                                        <td style={{ padding: '9px 12px' }}><StatusBadge record={p} /></td>
                                                        <td style={{ padding: '9px 12px', fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--muted)' }}>{p.processing_plan_name || '—'}</td>
                                                    </tr>
                                                    {isExpanded && p.components?.map((c, ci) => (
                                                        <tr key={`${p.article}_${c.material_id}`} style={{ borderBottom: '1px solid var(--hairline)', backgroundColor: 'var(--surface-card)' }}>
                                                            <td colSpan={6} style={{ padding: '7px 12px 7px 52px' }}>
                                                                <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted-soft)', flexShrink: 0 }}>{ci + 1}</span>
                                                                    <span style={{ fontFamily: 'var(--sans)', fontSize: '12px', color: 'var(--ink)', flex: 1 }}>{c.material_name}</span>
                                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted)', flexShrink: 0 }}>{c.uom}</span>
                                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: '11px', color: 'var(--muted)', flexShrink: 0 }}>на ед.: {c.quantity_per_recipe?.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</span>
                                                                    <span style={{ fontFamily: 'var(--mono)', fontSize: '12px', color: 'var(--ink)', flexShrink: 0, fontWeight: 500 }}>итого: {c.total_quantity?.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}</span>
                                                                </div>
                                                            </td>
                                                        </tr>
                                                    ))}
                                                </Fragment>
                                            );
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )}
                </>
            )}

            {/* Toast notification */}
            {notice && (
                <div style={{ position: 'fixed', bottom: '24px', right: '24px', zIndex: 100, backgroundColor: noticeColors[notice.type] || 'var(--surface-dark)', color: '#fff', borderRadius: '8px', padding: '10px 16px', fontFamily: 'var(--sans)', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', boxShadow: '0 4px 12px rgba(20,20,19,0.2)' }}>
                    {notice.type === 'loading' && <Loader2 style={{ width: 14, height: 14 }} className="animate-spin" />}
                    {notice.text}
                </div>
            )}
        </div>
    );
};

export default ProductionCalculator;
