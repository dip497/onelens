import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from 'sonner';

// Layout
import { MainLayout } from '@/components/layout/MainLayout';

// Pages
import { EpicDashboard } from '@/components/epics/EpicDashboard';
import { EpicDetail } from '@/pages/EpicDetail';
import { EditEpic } from '@/pages/EditEpic';
import { FeatureDashboard } from '@/pages/FeatureDashboard';
import { FeatureAnalysis } from '@/pages/FeatureAnalysis';
import { AnalysisReports } from '@/pages/AnalysisReports';
import { CompetitorAnalysis } from '@/pages/CompetitorAnalysis';
import { CustomerInsights } from '@/pages/CustomerInsights';
import CustomersPage from '@/pages/customers';
import { AgentPage } from '@/pages/AgentPage';
import { NotFound } from '@/pages/NotFound';
import RFPDashboard from '@/components/rfp/RFPDashboard';
import { PersonaDashboard } from '@/components/personas/PersonaDashboard';
import { ProductDetail } from '@/pages/ProductDetail';
import { BattleCardBuilder } from '@/pages/BattleCardBuilder';
import { BattleCardView } from '@/pages/BattleCardView';

// Create a client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>
          <Route path="/" element={<MainLayout />}>
            <Route index element={<Navigate to="/epics" replace />} />
            <Route path="epics" element={<EpicDashboard />} />
            <Route path="epics/:id" element={<EpicDetail />} />
            <Route path="epics/:id/edit" element={<EditEpic />} />
            <Route path="features" element={<FeatureDashboard />} />
            <Route path="features/:featureId/analysis" element={<FeatureAnalysis />} />
            <Route path="rfp" element={<RFPDashboard />} />
            <Route path="analysis" element={<AnalysisReports />} />
            <Route path="competitors" element={<CompetitorAnalysis />} />
            <Route path="customers" element={<CustomersPage />} />
            <Route path="customer-insights" element={<CustomerInsights />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="personas" element={<PersonaDashboard />} />
            <Route path="personas/:productId" element={<ProductDetail />} />
            <Route path="personas/:productId/battle-cards/new" element={<BattleCardBuilder />} />
            <Route path="personas/:productId/battle-cards/:battleCardId" element={<BattleCardView />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Router>
      <Toaster position="bottom-right" richColors />
      {/* <ReactQueryDevtools initialIsOpen={false} /> */}
    </QueryClientProvider>
  );
}

export default App;