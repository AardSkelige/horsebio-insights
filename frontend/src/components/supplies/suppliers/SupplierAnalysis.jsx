import { RefreshCw } from 'lucide-react';
import SupplierFilterPanel from './SupplierFilterPanel';
import SupplierTable from './SupplierTable';
import SupplierStatistics from './SupplierStatistics';
import SupplierDetailsModal from './SupplierDetailsModal';
import SectionLabel from '../../ui/SectionLabel';
import { FadeRise } from '../../ui/motion';
import { suppliesApi } from '../../../api/suppliesApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', startDate: null, endDate: null };

const SupplierAnalysis = () => {
    const {
        rows: suppliers, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem: selectedSupplier, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh,
    } = useAnalysisTable({
        fetchFn: suppliesApi.suppliers.getList,
        dataKey: 'suppliers',
        defaultSort: 'total_sum',
        defaultFilters: DEFAULT_FILTERS,
    });

    return (
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 0 40px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '0 0 16px', borderBottom: '1px solid var(--hairline)', marginBottom: 24 }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 400, letterSpacing: '-0.025em', color: 'var(--ink)', margin: 0 }}>
                    Поставщики
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
                <SupplierFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

            {stats && (
                <FadeRise delay={0.05} style={{ marginBottom: 24 }}>
                    <SectionLabel>Сводка</SectionLabel>
                    <SupplierStatistics stats={stats} />
                </FadeRise>
            )}

            <FadeRise delay={0.1}>
                <SupplierTable
                    suppliers={suppliers}
                    loading={loading}
                    pagination={pagination}
                    sortField={sortField}
                    sortOrder={sortOrder}
                    onSort={handleSort}
                    onPageChange={handlePageChange}
                    onSupplierClick={handleItemClick}
                />
            </FadeRise>

            {selectedSupplier && (
                <SupplierDetailsModal
                    supplier={selectedSupplier}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    startDate={filters.startDate}
                    endDate={filters.endDate}
                />
            )}
        </div>
    );
};

export default SupplierAnalysis;
