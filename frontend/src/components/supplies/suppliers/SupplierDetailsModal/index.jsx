import { useState, useEffect } from 'react';
import { num } from '../../../../utils/formatters';
import { CloseButton, MultiSelect, SectionLabel } from '../../../ui';
import PropTypes from 'prop-types';
import { ChevronRight, Loader2 } from 'lucide-react';
import StatisticsSection from './StatisticsSection';
import MaterialsSection from './MaterialsSection';
import PriceChart from './PriceChart';
import { ModalShell } from '../../../ui/motion';
import { suppliesApi } from '../../../../api/suppliesApi';


/* Материалы на графике: значения числовые, поэтому приводим их к строкам
   для примитива и обратно — наружу компонент отдаёт те же числа */
const MaterialMultiSelect = ({ options, value, onChange }) => (
    <MultiSelect
        block
        placeholder="Выберите материалы для графика"
        formatSelected={(n) => `Выбрано материалов: ${n}`}
        options={options.map((o) => ({ value: String(o.value), label: o.label, hint: o.code }))}
        value={value.map(String)}
        onChange={(next) => onChange(next.map(Number))}
    />
);

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
                <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--primary)', fontWeight: 500, padding: '8px 10px', borderBottom: '1px solid var(--hairline-soft)', textAlign: 'right' }}>{num(supply.sum)} ₽</td>
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
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{num(item.quantity)} {item.uom}</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{num(item.price)} ₽</td>
                                        <td style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--body)', padding: '6px 8px' }}>{num(item.total)} ₽</td>
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

    const allMaterials = details
        ? Object.values(details.categories).flatMap(c => c.materials || []).sort((a, b) => a.name.localeCompare(b.name))
        : [];

    const materialOptions = allMaterials.map(m => ({ value: m.id, label: m.name, code: m.code }));
    const selectedMaterialsData = allMaterials.filter(m => selectedMaterials.includes(m.id));

    const thStyle = { fontFamily: 'var(--sans)', fontSize: '11px', fontWeight: 500, letterSpacing: '0.07em', textTransform: 'uppercase', color: 'var(--muted)', padding: '7px 10px', textAlign: 'left', borderBottom: '1px solid var(--hairline)', background: 'var(--canvas)' };

    return (
        <ModalShell open={visible} onClose={onClose} maxWidth={1080}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '20px 24px 16px', borderBottom: '1px solid var(--hairline)', flexShrink: 0 }}>
                    <h2 style={{ fontFamily: 'var(--serif)', fontSize: 22, fontWeight: 400, letterSpacing: '-0.02em', color: 'var(--ink)', margin: 0 }}>
                        {supplier?.name}
                    </h2>
                    <CloseButton onClick={onClose} />
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
        </ModalShell>
    );
};

SupplierDetailsModal.propTypes = {
    supplier: PropTypes.shape({ id: PropTypes.number, name: PropTypes.string }),
    visible: PropTypes.bool.isRequired,
    onClose: PropTypes.func.isRequired,
    startDate: PropTypes.string,
    endDate: PropTypes.string,
};

export default SupplierDetailsModal;
