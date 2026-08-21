import SupplierFilterPanel from './SupplierFilterPanel';
import SupplierTable from './SupplierTable';
import SupplierStatistics from './SupplierStatistics';
import SupplierDetailsModal from './SupplierDetailsModal';
import { Page, PageHeader, StatGrid } from '../../ui';
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
        <Page>
            <PageHeader title="Поставщики" onRefresh={refresh} refreshing={loading} />

            <FadeRise>
                {stats ? <SupplierStatistics stats={stats} /> : <StatGrid loading count={4} />}
            </FadeRise>

            <FadeRise delay={0.05}>
                <SupplierFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

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
        </Page>
    );
};

export default SupplierAnalysis;
