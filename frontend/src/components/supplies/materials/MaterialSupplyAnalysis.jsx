import MaterialSupplyFilterPanel from './MaterialSupplyFilterPanel';
import { num } from '../../../utils/formatters';
import MaterialSupplyTable from './MaterialSupplyTable';
import MaterialSupplyDetailsModal from './MaterialSupplyDetailsModal';
import { Page, PageHeader, StatCard, StatGrid } from '../../ui';
import { FadeRise } from '../../ui/motion';
import { suppliesApi } from '../../../api/suppliesApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', group: '', startDate: null, endDate: null };


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
        <Page>
            <PageHeader title="Материалы в приёмках" onRefresh={refresh} refreshing={loading} />

            <FadeRise>
                {stats ? (
                    <StatGrid>
                        <StatCard title="Материалов" value={stats.total_materials} />
                        <StatCard title="Приёмок" value={stats.total_supplies} />
                        <StatCard title="Общая сумма" value={stats.total_sum ?? 0} format={(v) => `${num(v)} ₽`} />
                    </StatGrid>
                ) : <StatGrid loading count={3} />}
            </FadeRise>

            <FadeRise delay={0.05}>
                <MaterialSupplyFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

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
        </Page>
    );
};

export default MaterialSupplyAnalysis;
