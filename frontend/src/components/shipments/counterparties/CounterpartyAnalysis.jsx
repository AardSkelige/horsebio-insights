import CounterpartyFilterPanel from './CounterpartyFilterPanel';
import CounterpartyTable from './CounterpartyTable';
import CounterpartyStatistics from './CounterpartyStatistics';
import CounterpartyDetailsModal from './CounterpartyDetailsModal';
import { Page, PageHeader, StatGrid } from '../../ui';
import { FadeRise } from '../../ui/motion';
import { counterpartiesApi } from '../../../api/counterpartiesApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', startDate: null, endDate: null };

const CounterpartyAnalysis = () => {
    const {
        rows: counterparties, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem: selectedCounterparty, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh,
    } = useAnalysisTable({
        fetchFn: counterpartiesApi.getList,
        dataKey: 'counterparties',
        defaultSort: 'total_sales',
        defaultFilters: DEFAULT_FILTERS,
    });

    return (
        <Page>
            <PageHeader
                title="Покупатели"
                subtitle="Анализ продаж по контрагентам"
                onRefresh={refresh}
                refreshing={loading}
            />

            <FadeRise>
                {stats ? <CounterpartyStatistics stats={stats} /> : <StatGrid loading count={5} />}
            </FadeRise>

            <FadeRise delay={0.05}>
                <CounterpartyFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

            <FadeRise delay={0.1}>
                <CounterpartyTable
                    counterparties={counterparties}
                    loading={loading}
                    pagination={pagination}
                    sortField={sortField}
                    sortOrder={sortOrder}
                    onSort={handleSort}
                    onPageChange={handlePageChange}
                    onCounterpartyClick={handleItemClick}
                />
            </FadeRise>

            {selectedCounterparty && (
                <CounterpartyDetailsModal
                    counterparty={selectedCounterparty}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </Page>
    );
};

export default CounterpartyAnalysis;
