import { Download } from 'lucide-react';
import ProductFilterPanel from './ProductFilterPanel';
import ProductTable from './ProductTable';
import ProductStatistics from './ProductStatistics';
import ProductDetailsModal from './ProductDetailsModal';
import { Button, Page, PageHeader, StatGrid } from '../../ui';
import { FadeRise } from '../../ui/motion';
import { productsApi } from '../../../api/productsApi';
import { useAnalysisTable } from '../../../hooks/useAnalysisTable';

const DEFAULT_FILTERS = { search: '', subgroup: '', salesChannel: '', startDate: null, endDate: null };

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

    // Выгрузка идёт с теми же фильтрами, что и таблица: иначе в файле окажется
    // не то, что человек видит на экране
    const handleExport = () => {
        const params = new URLSearchParams();
        if (filters.search) params.append('search', filters.search);
        if (filters.subgroup) params.append('subgroup', filters.subgroup);
        if (filters.salesChannel) params.append('salesChannel', filters.salesChannel);
        if (filters.startDate) params.append('startDate', filters.startDate);
        if (filters.endDate) params.append('endDate', filters.endDate);

        const link = document.createElement('a');
        link.href = `/api/products/export/?${params}`;
        link.download = 'products_export.xlsx';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    };

    return (
        <Page>
            <PageHeader
                title="Товары в отгрузках"
                onRefresh={refresh}
                refreshing={loading}
                actions={
                    <Button variant="quiet" icon={Download} onClick={handleExport}>
                        Экспорт
                    </Button>
                }
            />

            <FadeRise>
                {stats ? <ProductStatistics stats={stats} /> : <StatGrid loading count={3} min={300} />}
            </FadeRise>

            <FadeRise delay={0.05}>
                <ProductFilterPanel filters={filters} onChange={handleFiltersChange} />
            </FadeRise>

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
                    salesChannel={filters.salesChannel}
                />
            )}
        </Page>
    );
};

export default ProductAnalysis;
