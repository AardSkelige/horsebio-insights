import { RefreshCw } from 'lucide-react';
import CounterpartyFilterPanel from './CounterpartyFilterPanel';
import CounterpartyTable from './CounterpartyTable';
import CounterpartyStatistics from './CounterpartyStatistics';
import CounterpartyDetailsModal from './CounterpartyDetailsModal';
import SectionLabel from '../../ui/SectionLabel';
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 32, color: 'var(--ink)' }}>
            <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: 16, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                    <h1 style={{ fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 400, letterSpacing: '-0.025em', lineHeight: 1.1, color: 'var(--ink)', margin: 0, marginBottom: 4 }}>
                        Покупатели
                    </h1>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: 13, color: 'var(--muted)', margin: 0 }}>
                        Анализ продаж по контрагентам
                    </p>
                </div>
                <button
                    onClick={refresh}
                    disabled={loading}
                    style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 8, border: 'none', background: 'var(--surface-card)', color: 'var(--ink)', fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1 }}
                >
                    <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                    Обновить
                </button>
            </div>

            {stats && (
                <section>
                    <SectionLabel>Статистика</SectionLabel>
                    <CounterpartyStatistics stats={stats} />
                </section>
            )}

            <section>
                <SectionLabel>Контрагенты</SectionLabel>
                <CounterpartyFilterPanel filters={filters} onChange={handleFiltersChange} />
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
            </section>

            {selectedCounterparty && (
                <CounterpartyDetailsModal
                    counterparty={selectedCounterparty}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </div>
    );
};

export default CounterpartyAnalysis;
