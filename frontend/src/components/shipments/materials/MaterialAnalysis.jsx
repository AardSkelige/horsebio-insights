import MaterialFilterPanel from './MaterialFilterPanel';
import MaterialTable from './MaterialTable';
import MaterialStatistics from './MaterialStatistics';
import MaterialDetailsModal from './MaterialDetailsModal';
import { Page, PageHeader, StatGrid } from '../../ui';
import { FadeRise } from '../../ui/motion';
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
        <Page>
            <PageHeader title="Материалы в отгрузках" onRefresh={refresh} refreshing={loading} />

            <FadeRise>
                {stats ? <MaterialStatistics stats={stats} /> : <StatGrid loading count={3} />}
            </FadeRise>

            <FadeRise delay={0.05}>
                <MaterialFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

            <FadeRise delay={0.1}>
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
            </FadeRise>

            {selectedMaterial && (
                <MaterialDetailsModal
                    material={selectedMaterial}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </Page>
    );
};

export default MaterialAnalysis;
