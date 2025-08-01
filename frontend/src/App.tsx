import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { Toaster } from 'sonner';

// Layout
import { MainLayout } from '@/components/layout/MainLayout';

// Pages
import { EpicDashboard } from '@/components/epics/EpicDashboard';
import { EpicDetail } from '@/pages/EpicDetail';
import { FeatureDashboard } from '@/pages/FeatureDashboard';
import { AnalysisReports } from '@/pages/AnalysisReports';
import { CompetitorAnalysis } from '@/pages/CompetitorAnalysis';
import { CustomerInsights } from '@/pages/CustomerInsights';
import { AgentPage } from '@/pages/AgentPage';
import { NotFound } from '@/pages/NotFound';

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
            <Route path="features" element={<FeatureDashboard />} />
            <Route path="analysis" element={<AnalysisReports />} />
            <Route path="competitors" element={<CompetitorAnalysis />} />
            <Route path="customers" element={<CustomerInsights />} />
            <Route path="agent" element={<AgentPage />} />
            <Route path="*" element={<NotFound />} />
          </Route>
        </Routes>
      </Router>
      <Toaster position="bottom-right" richColors />
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}

export default App;