import { useState, useEffect } from 'react';
import { Page, PageHeader, Skeleton } from '../ui';
import { Package, AlertTriangle } from 'lucide-react';
import SupplierAnalysisCard from './components/SupplierAnalysisCard';
import PurchaseRecommendations from './components/PurchaseRecommendations';
import PurchaseVerdict from './components/PurchaseVerdict';
import RelatedMaterialsTable from './components/RelatedMaterialsTable';
import MaterialSearchPanel from './components/MaterialSearchPanel';
import QuickInsightsCard from './components/QuickInsightsCard';
import { FadeRise, Stagger, StaggerItem } from '../ui/motion';
import { materialsApi } from '../../api/materialsApi';
import { analysisApi } from '../../api/analysisApi';

const PurchaseAnalysis = () => {
    const [loading, setLoading] = useState(false);
    const [materials, setMaterials] = useState([]);
    const [selectedMaterial, setSelectedMaterial] = useState(null);
    const [analysisData, setAnalysisData] = useState(null);
    const [error, setError] = useState(null);
    const [activityThreshold, setActivityThreshold] = useState(6);
    const [showInactive, setShowInactive] = useState(false);

    const fetchMaterials = async (search = '') => {
        try {
            const data = await materialsApi.getList(new URLSearchParams({ search }));
            if (data.status === 'success') setMaterials(data.data.materials || []);
        } catch { /* silent */ }
    };

    const fetchAnalysis = async (materialId) => {
        setLoading(true);
        setError(null);
        try {
            const data = await analysisApi.purchase.getMaterial(materialId);
            if (data.status === 'success') {
                setAnalysisData(data.data);
            } else {
                setAnalysisData(null);
                setError(data.message || 'Не удалось рассчитать анализ по этому материалу');
            }
        } catch (err) {
            setAnalysisData(null);
            setError(err.message || 'Не удалось загрузить анализ. Попробуйте позже.');
        }
        finally { setLoading(false); }
    };

    useEffect(() => { fetchMaterials(); }, []);
    useEffect(() => { if (selectedMaterial) fetchAnalysis(selectedMaterial.id); }, [selectedMaterial]);

    return (
        <Page>
            <PageHeader title="Помощник закупок" subtitle="Оптимизация и рекомендации по материалам" />

            <FadeRise>
                <MaterialSearchPanel materials={materials} onSearch={fetchMaterials} onSelect={setSelectedMaterial} />
            </FadeRise>

            {loading && !analysisData && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }} aria-busy="true">
                    <Skeleton height={180} style={{ borderRadius: 10 }} />
                    <Skeleton height={64} style={{ borderRadius: 10 }} />
                    <Skeleton height={64} style={{ borderRadius: 10 }} />
                </div>
            )}

            {!selectedMaterial && !loading && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '64px 0', gap: '10px' }}>
                    <Package style={{ width: 40, height: 40, color: 'var(--hairline)' }} />
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--ink)', margin: 0 }}>Выберите материал для анализа</p>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0 }}>Найдите материал в поиске выше</p>
                </div>
            )}

            {selectedMaterial && !loading && !analysisData && error && (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '64px 0', gap: '10px' }}>
                    <AlertTriangle style={{ width: 40, height: 40, color: 'var(--muted)' }} />
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '14px', fontWeight: 500, color: 'var(--ink)', margin: 0 }}>Не удалось построить анализ</p>
                    <p style={{ fontFamily: 'var(--sans)', fontSize: '13px', color: 'var(--muted)', margin: 0, maxWidth: '420px', textAlign: 'center' }}>{error}</p>
                </div>
            )}

            {selectedMaterial && analysisData && (
                <Stagger style={{ display: 'flex', flexDirection: 'column', gap: '16px', opacity: loading ? 0.45 : 1, pointerEvents: loading ? 'none' : 'auto', transition: 'opacity 200ms ease' }}>
                    <StaggerItem>
                        <PurchaseVerdict analysisData={analysisData} material={analysisData.material} />
                    </StaggerItem>
                    <StaggerItem>
                        <QuickInsightsCard analysisData={analysisData} material={analysisData.material} onPeriodChange={() => fetchAnalysis(selectedMaterial.id)} />
                    </StaggerItem>
                    <StaggerItem>
                        <SupplierAnalysisCard suppliers={analysisData.suppliers || {}} material={analysisData.material} activityThreshold={activityThreshold} setActivityThreshold={setActivityThreshold} showInactive={showInactive} setShowInactive={setShowInactive} />
                    </StaggerItem>
                    <StaggerItem>
                        <PurchaseRecommendations recommendations={analysisData.recommendations} material={analysisData.material} generalCalculations={analysisData.general_calculations} suppliers={analysisData.suppliers || {}} activityThreshold={activityThreshold} showInactive={showInactive} />
                    </StaggerItem>
                    <StaggerItem>
                        <RelatedMaterialsTable relatedData={analysisData.related_materials} suppliers={analysisData.suppliers || {}} activityThreshold={activityThreshold} showInactive={showInactive} />
                    </StaggerItem>
                </Stagger>
            )}
        </Page>
    );
};

export default PurchaseAnalysis;
