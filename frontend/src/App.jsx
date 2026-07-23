// frontend/src/App.jsx
import { lazy, Suspense } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import PropTypes from 'prop-types';
import Layout from './components/layout/Layout';
import { MotionProvider } from './components/ui/motion';
import { LoadingProvider } from './contexts/LoadingContext';
import { DataPanelProvider } from './contexts/DataPanelContext';
import LoginPage from './components/auth/LoginPage';
import ProtectedRoute from './components/auth/ProtectedRoute';
import SuperuserRoute from './components/auth/SuperuserRoute';
import PageAccessGuard from './components/auth/PageAccessGuard';

const LayoutWrapper = ({ children }) => <Layout><PageAccessGuard>{children}</PageAccessGuard></Layout>;

const HomePage = lazy(() => import('./components/home/HomePage'));
const ProductAnalysis = lazy(() => import('./components/shipments/products/ProductAnalysis'));
const CounterpartyAnalysis = lazy(() => import('./components/shipments/counterparties/CounterpartyAnalysis'));
const MaterialAnalysis = lazy(() => import('./components/shipments/materials/MaterialAnalysis'));
const MaterialSupplyAnalysis = lazy(() => import('./components/supplies/materials/MaterialSupplyAnalysis'));
const SupplierAnalysis = lazy(() => import('./components/supplies/suppliers/SupplierAnalysis'));
const PurchaseAnalysis = lazy(() => import('./components/purchases/PurchaseAnalysis'));
const ABCAnalysis = lazy(() => import('./components/abc/ABCAnalysis').then(module => ({ default: module.ABCAnalysis })));
const SeasonalAnalysis = lazy(() => import('./components/seasonality/SeasonalAnalysis').then(module => ({ default: module.SeasonalAnalysis })));
const CounterpartyGroupsAnalysis = lazy(() => import('./components/counterparty-groups/CounterpartyGroupsAnalysis'));
const FBOAnalysis = lazy(() => import('./components/fbo-analysis/FBOAnalysis'));
const OzonAnalytics = lazy(() => import('./components/ozon-analytics/OzonAnalytics'));
const CashFlowReport = lazy(() => import('./components/cash-flow/CashFlowReport'));
const CashFlowReportV2 = lazy(() => import('./components/cash-flow/CashFlowReportV2'));
const ProductionCalculator = lazy(() => import('./components/production/ProductionCalculator'));
const FboConverter = lazy(() => import('./components/fbo-converter/FboConverter'));
const ChecksPage = lazy(() => import('./components/checks/ChecksPage'));
const ProfilePage = lazy(() => import('./components/profile/ProfilePage'));
const AdminAnalyticsPage = lazy(() => import('./components/admin-analytics/AdminAnalyticsPage'));
const AccessAdminPage = lazy(() => import('./components/admin-access/AccessAdminPage'));
const InventoryTracking = lazy(() => import('./components/inventory-tracking/InventoryTracking'));
const PaymentDeadlinesPage = lazy(() => import('./components/payment-deadlines/PaymentDeadlinesPage'));
const SiteOrdersPage = lazy(() => import('./components/site-orders/SiteOrdersPage'));

const RouteFallback = () => (
  <div aria-busy="true" aria-label="Загрузка раздела" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
    <div className="skeleton" style={{ width: 220, height: 32 }} />
    <div className="skeleton" style={{ height: 56 }} />
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
      <div className="skeleton" style={{ height: 88 }} />
      <div className="skeleton" style={{ height: 88 }} />
      <div className="skeleton" style={{ height: 88 }} />
    </div>
    <div className="skeleton" style={{ height: 240 }} />
  </div>
);

const LazyPage = ({ children }) => (
  <Suspense fallback={<RouteFallback />}>
    {children}
  </Suspense>
);

function AppRoutes() {
  return (
      <Routes>
        {/* Публичный роут для страницы логина */}
        <Route path="/login" element={<LoginPage />} />

        {/* Защищенные роуты */}
        <Route path="/" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <HomePage />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        {/* Маршруты для отгрузок */}
        <Route path="/shipments" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <div className="card">Обзор отгрузок</div>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/shipments/products" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <ProductAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/shipments/counterparties" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <CounterpartyAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/shipments/materials" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <MaterialAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/purchases/analysis" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <PurchaseAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        {/* Маршруты для приемок */}
        <Route path="/supplies" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <div className="card">Обзор приемок</div>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/supplies/materials" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <MaterialSupplyAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/supplies/suppliers" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <SupplierAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        {/* Маршруты для анализа */}
        <Route path="/analysis/abc" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <ABCAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/seasonal" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <SeasonalAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/fbo" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <FBOAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/counterparty-groups" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <CounterpartyGroupsAnalysis />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/ozon" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <OzonAnalytics />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/cash-flow" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <CashFlowReport />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/analysis/cash-flow-v2" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <CashFlowReportV2 />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/production/calculator" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <ProductionCalculator />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/ozon/fbo-converter" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <FboConverter />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/checks" element={
          <SuperuserRoute>
            <LayoutWrapper>
              <LazyPage>
                <ChecksPage />
              </LazyPage>
            </LayoutWrapper>
          </SuperuserRoute>
        } />

        <Route path="/checks/:scriptId" element={
          <SuperuserRoute>
            <LayoutWrapper>
              <LazyPage>
                <ChecksPage />
              </LazyPage>
            </LayoutWrapper>
          </SuperuserRoute>
        } />

        <Route path="/inventory" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <InventoryTracking />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/profile" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <ProfilePage />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/deadlines" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <PaymentDeadlinesPage />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/site-orders" element={
          <ProtectedRoute>
            <LayoutWrapper>
              <LazyPage>
                <SiteOrdersPage />
              </LazyPage>
            </LayoutWrapper>
          </ProtectedRoute>
        } />

        <Route path="/system/analytics" element={
          <SuperuserRoute>
            <LayoutWrapper>
              <LazyPage>
                <AdminAnalyticsPage />
              </LazyPage>
            </LayoutWrapper>
          </SuperuserRoute>
        } />

        <Route path="/system/access" element={
          <SuperuserRoute>
            <LayoutWrapper>
              <LazyPage>
                <AccessAdminPage />
              </LazyPage>
            </LayoutWrapper>
          </SuperuserRoute>
        } />
      </Routes>
  );
}

function App() {
  return (
    <MotionProvider>
      <LoadingProvider>
        <DataPanelProvider>
        <Router>
          <AppRoutes />
        </Router>
        </DataPanelProvider>
      </LoadingProvider>
    </MotionProvider>
  );
}

LayoutWrapper.propTypes = {
  children: PropTypes.node.isRequired
};

LazyPage.propTypes = {
  children: PropTypes.node.isRequired
};

export default App;
