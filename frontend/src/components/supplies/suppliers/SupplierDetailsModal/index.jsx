import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import PropTypes from 'prop-types';
import { X, ChevronRight, Loader2, Check, Search, ChevronDown } from 'lucide-react';
import StatisticsSection from './StatisticsSection';
import MaterialsSection from './MaterialsSection';
import PriceChart from './PriceChart';
import SectionLabel from '../../../ui/SectionLabel';
import { suppliesApi } from '../../../../api/suppliesApi';

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

/* Мульти-селект для материалов на графике */
const MaterialMultiSelect = ({ options, value, onChange }) => {
    const [open, setOpen] = useState(false);
    const [search, setSearch] = useState('');
    const ref = useRef(null);

    useEffect(() => {
        const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const filtered = options.filter(o =>
        o.label.toLowerCase().includes(search.toLowerCase()) ||
        (o.code || '').toLowerCase().includes(search.toLowerCase())
    );
    const toggle = (id) => {
        const next = value.includes(id) ? value.filter(v => v !== id) : [...value, id];
        onChange(next);
    };

    return (
        <div ref={ref} style={{ position: 'relative', marginBottom: 12 }}>
            <button type="button" onClick={() => setOpen(o => !o)}
                style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--ink)', background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, padding: '7px 12px', outline: 'none', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', width: '100%', justifyContent: 'space-between' }}>
                <span style={{ color: value.length ? 'var(--ink)' : 'var(--muted)' }}>
                    {value.length ? `Выбрано материалов: ${value.length}` : 'Выберите материалы для графика'}
                </span>
                <ChevronDown size={12} style={{ color: 'var(--muted)', transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 150ms' }} />
            </button>
            {open && (
                <div style={{ position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 200, background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 8, boxShadow: '0 4px 16px rgba(20,20,19,0.1)', maxHeight: 260, display: 'flex', flexDirection: 'column' }}>
                    <div style={{ padding: '8px 10px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                        <div style={{ position: 'relative' }}>
                            <Search size={12} style={{ position: 'absolute', left: 8, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
                            <input autoFocus
                                style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', background: 'var(--canvas)', border: '1px solid var(--hairline)', borderRadius: 6, padding: '5px 8px 5px 26px', outline: 'none', width: '100%', boxSizing: 'border-box' }}
                                placeholder="Поиск..."
                                value={search}
                                onChange={e => setSearch(e.target.value)}
                            />
                        </div>
                    </div>
                    <div style={{ overflowY: 'auto' }}>
                        {filtered.map(o => (
                            <div key={o.value} onClick={() => toggle(o.value)}
                                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 12px', cursor: 'pointer', fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', background: value.includes(o.value) ? 'var(--surface-soft)' : 'transparent' }}
                                onMouseEnter={e => { if (!value.includes(o.value)) e.currentTarget.style.background = 'var(--surface-soft)'; }}
                                onMouseLeave={e => { if (!value.includes(o.value)) e.currentTarget.style.background = 'transparent'; }}
                            >
                                <div style={{ width: 14, height: 14, borderRadius: 3, border: `1px solid ${value.includes(o.value) ? 'var(--primary)' : 'var(--hairline)'}`, background: value.includes(o.value) ? 'var(--primary)' : 'transparent', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                    {value.includes(o.value) && <Check size={9} style={{ color: '#fff' }} />}
                                </div>
                                <span>{o.label}</span>
                                {o.code && <span style={{ color: 'var(--muted)', marginLeft: 'auto', fontFamily: 'var(--mono)', fontSize: 11 }}>{o.code}</span>}
                            </div>
                        ))}
                        {filtered.length === 0 && <div style={{ padding: '10px 14px', fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Ничего не найдено</div>}
                    </div>
                    {value.length > 0 && (
                        <div style={{ padding: '6px 10px', borderTop: '1px solid var(--hairline)' }}>
                            <button onClick={() => { onChange([]); setOpen(false); }} style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}>
                                Сбросить выбор
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};
MaterialMultiSelect.propTypes = {
    options: PropTypes.arrayOf(PropTypes.shape({ value: PropTypes.number, label: PropTypes.string, code: PropTypes.string })).isRequired,
    value: PropTypes.arrayOf(PropTypes.number).isRequired,
    onChange: PropTypes.func.isRequired,
};

/* Строка истории приёмок */
const SupplyRow = ({ supply }) => {
    const [open, setOpen] = useState(false);
    return (
        <>
            <tr onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-soft)'}
                onMouseLeave={e => e.currentTarget.style.background = ''}>
                <td style={{ padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)', width: 20 }}>
                    <ChevronRight size={12} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }} />
                </td>
                <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)' }}>{supply.number}</td>
                <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)' }}>{supply.date}</td>
                <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)' }}>{supply.items_count} позиций</td>
                <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--primary)', fontWeight: 500, padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)', textAlign: 'right' }}>{fmt(supply.sum)} ₽</td>
            </tr>
            {open && supply.items?.length > 0 && (
                <tr>
                    <td colSpan={5} style={{ padding: '8px 14px 12px', background: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline-soft)' }}>
                        <div style={{ overflowX: 'auto' }}>
                        <table style={{ width: '100%', minWidth: 420, borderCollapse: 'collapse' }}>
                            <thead>
                                <tr>
                                    {['Материал', 'Группа', 'Количество', 'Цена', 'Сумма'].map(h => (
                                        <th key={h} style={{ fontFamily: 'var(--sans)', fontSize: 10, fontWeight: 500, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', padding: '4px 8px', textAlign: 'left', borderBottom: '1px solid var(--hairline)' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {supply.items.map((item, i) => (
                                    <tr key={i}>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)', padding: '6px 8px' }}>{item.material_name}</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 11, color: 'var(--muted)', padding: '6px 8px' }}>{item.material_group || '—'}</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{fmt(item.quantity)} {item.uom}</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{fmt(item.price)} ₽</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{fmt(item.total)} ₽</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
};
SupplyRow.propTypes = {
    supply: PropTypes.shape({ number: PropTypes.string, date: PropTypes.string, sum: PropTypes.number, items_count: PropTypes.number, items: PropTypes.array }).isRequired,
};

const SupplierDetailsModal = ({ supplier, visible, onClose, startDate, endDate }) => {
    const [loading, setLoading] = useState(false);
    const [details, setDetails] = useState(null);
    const [selectedMaterials, setSelectedMaterials] = useState([]);

    useEffect(() => {
        if (!supplier?.id || !visible) return;
        const ctrl = new AbortController();
        setLoading(true);
        setDetails(null);
        setSelectedMaterials([]);

        const params = new URLSearchParams();
        if (startDate) params.append('startDate', startDate);
        if (endDate)   params.append('endDate',   endDate);
        const qs = params.toString();

        suppliesApi.suppliers.getDetails(supplier.id, qs, ctrl.signal)
            .then(data => {
                if (data.status === 'success') {
                    setDetails(data.data);
                    const all = Object.values(data.data.categories).flatMap(c => c.materials || []);
                    if (all.length > 0) setSelectedMaterials([all[0].id]);
                }
            })
            .catch(() => {})
            .finally(() => setLoading(false));

        return () => ctrl.abort();
    }, [supplier, visible, startDate, endDate]);

    if (!visible) return null;

    const allMaterials = details
        ? Object.values(details.categories).flatMap(c => c.materials || []).sort((a, b) => a.name.localeCompare(b.name))
        : [];

    const materialOptions = allMaterials.map(m => ({ value: m.id, label: m.name, code: m.code }));
    const selectedMaterialsData = allMaterials.filter(m => selectedMaterials.includes(m.id));

    const thStyle = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', padding: '7px 10px', textAlign: 'left', borderBottom: '1px solid var(--hairline)', background: 'var(--canvas)' };

    const modal = (
        <div style={{ position: 'fixed', inset: 0, zIndex: 9999, display: 'flex', alignItems: 'flex-start', justifyContent: 'center', padding: '40px 16px' }}>
            <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(20,20,19,0.55)' }} />
            <div style={{ position: 'relative', background: 'var(--canvas)', borderRadius: 16, border: '1px solid var(--hairline)', width: '100%', maxWidth: 1080, maxHeight: 'calc(100vh - 80px)', display: 'flex', flexDirection: 'column', boxShadow: '0 8px 40px rgba(20,20,19,0.18)' }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <h2 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0 }}>
                        {supplier?.name}
                    </h2>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4, flexShrink: 0 }}>
                        <X size={18} />
                    </button>
                </div>

                {/* Body */}
                <div style={{ overflowY: 'auto', padding: '20px 24px 24px', flex: 1 }}>
                    {loading ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 240, color: 'var(--muted)' }}>
                            <Loader2 size={20} className="animate-spin" />
                        </div>
                    ) : !details ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 120, fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)' }}>
                            Нет данных
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                            {/* Statistics */}
                            <div>
                                <SectionLabel>Статистика</SectionLabel>
                                <StatisticsSection statistics={details.statistics} />
                            </div>

                            {/* Price chart */}
                            <div>
                                <SectionLabel>Динамика цен</SectionLabel>
                                <MaterialMultiSelect
                                    options={materialOptions}
                                    value={selectedMaterials}
                                    onChange={setSelectedMaterials}
                                />
                                {selectedMaterialsData.length > 0
                                    ? <PriceChart materialsData={selectedMaterialsData} />
                                    : <div style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', padding: '16px 0' }}>Выберите материалы для отображения графика</div>
                                }
                            </div>

                            {/* Materials by category */}
                            <div>
                                <SectionLabel>Материалы</SectionLabel>
                                <MaterialsSection categories={details.categories} />
                            </div>

                            {/* Supply history */}
                            <div>
                                <SectionLabel>История приёмок</SectionLabel>
                                <div style={{ border: '1px solid var(--hairline)', borderRadius: 8, overflowX: 'auto' }}>
                                    <table style={{ width: '100%', minWidth: 380, borderCollapse: 'collapse' }}>
                                        <thead>
                                            <tr>
                                                <th style={{ ...thStyle, width: 20 }} />
                                                <th style={thStyle}>Номер</th>
                                                <th style={thStyle}>Дата</th>
                                                <th style={thStyle}>Позиции</th>
                                                <th style={{ ...thStyle, textAlign: 'right' }}>Сумма</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {details.supply_history?.map((s, i) => (
                                                <SupplyRow key={`${s.number || i}`} supply={s} />
                                            ))}
                                            {!details.supply_history?.length && (
                                                <tr><td colSpan={5} style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)', textAlign: 'center', padding: '20px 0' }}>Нет данных</td></tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );

    return createPortal(modal, document.body);
};

SupplierDetailsModal.propTypes = {
    supplier: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    startDate: PropTypes.string,
    endDate: PropTypes.string,
};

export default SupplierDetailsModal;
