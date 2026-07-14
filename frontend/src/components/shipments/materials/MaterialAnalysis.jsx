import { RefreshCw } from 'lucide-react';
import MaterialFilterPanel from './MaterialFilterPanel';
import MaterialTable from './MaterialTable';
import MaterialStatistics from './MaterialStatistics';
import MaterialDetailsModal from './MaterialDetailsModal';
import SectionLabel from '../../ui/SectionLabel';
import { materialsApi } from '../../../api/materialsApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', group: '', counterparties: [], startDate: null, endDate: null };

const MaterialAnalysis = () => {
    const {
        rows: materials, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem: selectedMaterial, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh,
    } = useAnalysisTable({
        fetchFn: materialsApi.getList,
        dataKey: 'materials',
        defaultSort: 'total_usage',
        defaultFilters: DEFAULT_FILTERS,
    });

    return (
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 0 40px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '0 0 16px', borderBottom: '1px solid var(--hairline)', marginBottom: 24 }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 400, letterSpacing: '-0.025em', color: 'var(--ink)', margin: 0 }}>
                    Материалы
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

            <MaterialFilterPanel filters={filters} onChange={handleFiltersChange} />

            {stats && (
                <div style={{ marginBottom: 24 }}>
                    <SectionLabel>Сводка</SectionLabel>
                    <MaterialStatistics stats={stats} />
                </div>
            )}

            <MaterialTable
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

            {selectedMaterial && (
                <MaterialDetailsModal
                    material={selectedMaterial}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </div>
    );
};

export default MaterialAnalysis;
