import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import AppLayout from "./components/layout/AppLayout";
import { FeatureAnalysis } from "./components/analysis/FeatureAnalysis";
import { MarketMonitoring } from "./components/monitoring/MarketMonitoring";
import { DemandDashboard } from "./components/demand/DemandDashboard";
import { BattleCardsGenerator } from "./components/battlecards/BattleCardsGenerator";
import NotFound from "./pages/NotFound";
import DashboardPage from "./pages/Dashboard";
import FeatureDetail from "./views/FeatureDetail";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
      storageKey="onelens-theme"
    >
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<AppLayout />}>
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<DashboardPage />} />
              <Route path="analysis" element={<FeatureAnalysis />} />
              <Route path="monitoring" element={<MarketMonitoring />} />
              <Route path="battlecards" element={<BattleCardsGenerator />} />
              <Route path="demand" element={<DemandDashboard />} />
              <Route path="/demand/feature-detail/:id" element={<FeatureDetail />} />

              {/* <Route path="alerts" element={<Alerts />} /> */}
              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </TooltipProvider>
    </ThemeProvider>
  </QueryClientProvider>
);

export default App;
