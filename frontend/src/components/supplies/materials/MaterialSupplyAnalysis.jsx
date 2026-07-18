import { RefreshCw } from 'lucide-react';
import MaterialSupplyFilterPanel from './MaterialSupplyFilterPanel';
import MaterialSupplyTable from './MaterialSupplyTable';
import MaterialSupplyDetailsModal from './MaterialSupplyDetailsModal';
import SectionLabel from '../../ui/SectionLabel';
import StatCard from '../../ui/StatCard';
import { FadeRise } from '../../ui/motion';
import { suppliesApi } from '../../../api/suppliesApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', group: '', startDate: null, endDate: null };

const fmt = (n) => (n ?? 0).toLocaleString('ru-RU');

const MaterialSupplyAnalysis = () => {
    const {
        rows: materials, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem: selectedMaterial, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh,
    } = useAnalysisTable({
        fetchFn: suppliesApi.materials.getList,
        dataKey: 'materials',
        defaultSort: 'total_quantity',
        defaultFilters: DEFAULT_FILTERS,
    });

    return (
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 0 40px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '0 0 16px', borderBottom: '1px solid var(--hairline)', marginBottom: 24 }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 400, letterSpacing: '-0.025em', color: 'var(--ink)', margin: 0 }}>
                    Приёмка материалов
                </h1>
                <button
                    onClick={refresh}
                    disabled={loading}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: loading ? 'var(--muted)' : 'var(--primary)', background: 'none', border: 'none', cursor: loading ? 'default' : 'pointer', padding: 0 }}
                >
                    <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
                    Обновить
                </button>
            </div>

            <FadeRise>
                <MaterialSupplyFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

            {stats && (
                <FadeRise delay={0.05} style={{ marginBottom: 24 }}>
                    <SectionLabel>Сводка</SectionLabel>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 12 }}>
                        <StatCard title="Материалов" value={stats.total_materials} />
                        <StatCard title="Приёмок" value={stats.total_supplies} />
                        <StatCard title="Общая сумма" value={stats.total_sum ?? 0} format={(v) => `${fmt(v)} ₽`} />
                    </div>
                </FadeRise>
            )}

            <FadeRise delay={0.1}>
                <MaterialSupplyTable
                    materials={materials}
                    loading={loading}
                    pagination={pagination}
                    sortField={sortField}
                    sortOrder={sortOrder}
                    onSort={handleSort}
                    onPageChange={handlePageChange}
                    onMaterialClick={handleItemClick}
                    filters={filters}
                />
            </FadeRise>

            {selectedMaterial && (
                <MaterialSupplyDetailsModal
                    material={selectedMaterial}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </div>
    );
};

export default MaterialSupplyAnalysis;
