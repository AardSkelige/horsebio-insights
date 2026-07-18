import { RefreshCw, Download } from 'lucide-react';
import ProductFilterPanel from './ProductFilterPanel';
import ProductTable from './ProductTable';
import ProductStatistics from './ProductStatistics';
import ProductDetailsModal from './ProductDetailsModal';
import SectionLabel from '../../ui/SectionLabel';
import { FadeRise } from '../../ui/motion';
import { productsApi } from '../../../api/productsApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', subgroup: '', startDate: null, endDate: null };

const ProductAnalysis = () => {
    const {
        rows: products, stats, loading, filters, pagination, sortField, sortOrder,
        selectedItem: selectedProduct, modalVisible,
        handleFiltersChange, handleSort, handlePageChange, handleItemClick, handleModalClose,
        refresh,
    } = useAnalysisTable({
        fetchFn: productsApi.getList,
        dataKey: 'products',
        defaultSort: 'total_sum',
        defaultFilters: DEFAULT_FILTERS,
    });

    const handleExport = () => {
        const params = new URLSearchParams();
        if (filters.search)    params.append('search',    filters.search);
        if (filters.subgroup)  params.append('subgroup',  filters.subgroup);
        if (filters.startDate) params.append('startDate', filters.startDate);
        if (filters.endDate)   params.append('endDate',   filters.endDate);
        const link = document.createElement('a');
        link.href = `/api/products/export/?${params}`;
        link.download = 'products_export.xlsx';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 0 40px' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', padding: '0 0 16px', borderBottom: '1px solid var(--hairline)', marginBottom: 24 }}>
                <h1 style={{ fontFamily: 'var(--serif)', fontSize: 32, fontWeight: 400, letterSpacing: '-0.025em', color: 'var(--ink)', margin: 0 }}>
                    Товары
                </h1>
                <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
                    <button
                        onClick={handleExport}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: 'var(--muted)', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                    >
                        <Download size={14} /> Экспорт
                    </button>
                    <button
                        onClick={refresh}
                        disabled={loading}
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--sans)', fontSize: 13, fontWeight: 500, color: loading ? 'var(--muted)' : 'var(--primary)', background: 'none', border: 'none', cursor: loading ? 'default' : 'pointer', padding: 0 }}
                    >
                        <RefreshCw size={14} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
                        Обновить
                    </button>
                </div>
            </div>

            <FadeRise>
                <ProductFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

            {stats && (
                <FadeRise delay={0.05} style={{ marginBottom: 24 }}>
                    <SectionLabel>Топ товаров</SectionLabel>
                    <ProductStatistics stats={stats} />
                </FadeRise>
            )}

            <FadeRise delay={0.1}>
                <ProductTable
                    products={products}
                    loading={loading}
                    pagination={pagination}
                    sortField={sortField}
                    sortOrder={sortOrder}
                    onSort={handleSort}
                    onPageChange={handlePageChange}
                    onProductClick={handleItemClick}
                />
            </FadeRise>

            {selectedProduct && (
                <ProductDetailsModal
                    product={selectedProduct}
                    visible={modalVisible}
                    onClose={handleModalClose}
                    dateRange={{ startDate: filters.startDate, endDate: filters.endDate }}
                />
            )}
        </div>
    );
};

export default ProductAnalysis;
