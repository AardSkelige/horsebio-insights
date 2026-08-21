import { useState } from 'react';
import { num } from '../../../../utils/formatters';
import PropTypes from 'prop-types';
import { m } from 'motion/react';
import { ChevronRight } from 'lucide-react';




const MaterialRow = ({ material }) => {
    const [open, setOpen] = useState(false);
    return (
        <>
            <tr
                onClick={() => setOpen(o => !o)}
                style={{ cursor: 'pointer', background: open ? 'var(--surface-soft)' : '' }}
                onMouseEnter={e => { if (!open) e.currentTarget.style.background = 'var(--surface-soft)'; }}
                onMouseLeave={e => { if (!open) e.currentTarget.style.background = ''; }}
            >
                <td style={{ paddingLeft: 6, width: 20 }}>
                    <ChevronRight size={12} style={{ color: 'var(--muted)', transform: open ? 'rotate(90deg)' : 'none', transition: 'transform 150ms' }} />
                </td>
                <td style={{ fontWeight: 500, color: 'var(--ink)' }}>{material.name}</td>
                <td style={{ fontFamily: 'var(--mono)', fontSize: 11 }}>{material.code}</td>
                <td>{num(material.total_quantity)} {material.uom}</td>
                <td>{num(material.avg_price)} ₽</td>
                <td>{num(material.last_price)} ₽</td>
                <td>{num(material.total_sum)} ₽</td>
            </tr>
            {open && (
                <tr>
                    <td colSpan={7} style={{ padding: '8px 14px 12px', background: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline-soft)' }}>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {material.supplies?.map((s, i) => (
                                <div key={i} style={{ background: 'var(--canvas)', borderRadius: 8, padding: '8px 12px', border: '1px solid var(--hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}>
                                    <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>{s.date}</span>
                                    <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--ink)' }}>
                                        {num(s.quantity)} {material.uom} · {(s.price || 0).toFixed(2)} ₽ · {num(s.total)} ₽
                                    </span>
                                </div>
                            ))}
                            {!material.supplies?.length && <span style={{ fontFamily: 'var(--sans)', fontSize: 12, color: 'var(--muted)' }}>Нет поставок</span>}
                        </div>
                    </td>
                </tr>
            )}
        </>
    );
};
MaterialRow.propTypes = {
    material: PropTypes.shape({
        name: PropTypes.string, code: PropTypes.string, uom: PropTypes.string,
        total_quantity: PropTypes.number, avg_price: PropTypes.number,
        last_price: PropTypes.number, total_sum: PropTypes.number,
        supplies: PropTypes.array,
    }).isRequired,
};

const MaterialsSection = ({ categories }) => {
    const allMaterials = Object.values(categories).flatMap(c => c.materials || []);
    const categoryEntries = Object.entries(categories);

    const [activeTab, setActiveTab] = useState('all');
    const tabs = [
        { key: 'all', label: `Все (${allMaterials.length})` },
        ...categoryEntries.map(([cat, data]) => ({ key: cat, label: `${cat} (${data.materials?.length || 0})` })),
    ];

    const currentMaterials = activeTab === 'all'
        ? allMaterials
        : (categories[activeTab]?.materials || []);

    return (
        <div>
            {/* Tabs */}
            <div style={{ display: 'flex', gap: 4, marginBottom: 12, flexWrap: 'wrap' }}>
                {tabs.map(tab => (
                    <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                        style={{ position: 'relative', fontFamily: 'var(--sans)', fontSize: 12, fontWeight: 500, padding: '5px 12px', borderRadius: 6, border: tab.key === activeTab ? '1px solid transparent' : '1px solid var(--hairline)', background: 'transparent', color: tab.key === activeTab ? 'var(--on-primary)' : 'var(--body)', cursor: 'pointer', transition: 'color 150ms ease' }}>
                        {tab.key === activeTab && (
                            <m.span
                                layoutId="materials-tabs-pill"
                                transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                                style={{ position: 'absolute', inset: -1, borderRadius: 6, background: 'var(--primary)' }}
                            />
                        )}
                        <span style={{ position: 'relative' }}>{tab.label}</span>
                    </button>
                ))}
            </div>

            {/* Table */}
            <div style={{ maxHeight: 400, overflowY: 'auto', border: '1px solid var(--hairline)', borderRadius: 8 }}>
                <table className="ui-table">
                    <thead>
                        <tr>
                            <th style={{ width: 20 }} />
                            <th>Наименование</th>
                            <th>Код</th>
                            <th>Количество</th>
                            <th>Средняя цена</th>
                            <th>Последняя цена</th>
                            <th>Общая сумма</th>
                        </tr>
                    </thead>
                    <tbody>
                        {currentMaterials.map(m => <MaterialRow key={m.id} material={m} />)}
                        {currentMaterials.length === 0 && (
                            <tr><td colSpan={7} style={{ textAlign: 'center', color: 'var(--muted)', padding: '20px 0' }}>Нет данных</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

MaterialsSection.propTypes = {
    categories: PropTypes.objectOf(PropTypes.shape({
        materials: PropTypes.array.isRequired,
        total_sum: PropTypes.number,
    })).isRequired,
};

export default MaterialsSection;
