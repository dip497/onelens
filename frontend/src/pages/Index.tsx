import { useState } from "react";
import { SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { Header } from "@/components/layout/Header";
import { DashboardWidgets } from "@/components/dashboard/DashboardWidgets";
import { FeatureAnalysis } from "@/components/analysis/FeatureAnalysis";
import { MarketMonitoring } from "@/components/monitoring/MarketMonitoring";
import { DemandDashboard } from "@/components/demand/DemandDashboard";
import { BattleCardsGenerator } from "@/components/battlecards/BattleCardsGenerator";
import { AIAssistant } from "@/components/ai/AIAssistant";

const Index = () => {
  const [activeSection, setActiveSection] = useState("dashboard");

  const renderContent = () => {
    switch (activeSection) {
      case "dashboard":
        return (
          <div className="space-y-6">
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-2">Dashboard</h1>
              <p className="text-muted-foreground">Welcome back! Here's your product intelligence overview.</p>
            </div>
            <DashboardWidgets />
          </div>
        );
      case "analysis":
        return (
          <div className="space-y-6">
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-2">Feature Analysis</h1>
              <p className="text-muted-foreground">Analyze features against competitive landscape with AI-powered insights.</p>
            </div>
            <FeatureAnalysis />
          </div>
        );
      case "monitoring":
        return <MarketMonitoring />;
      case "demand":
        return <DemandDashboard />;
      case "battlecards":
        return <BattleCardsGenerator />;
      case "alerts":
        return (
          <div className="space-y-6">
            <div>
              <h1 className="text-3xl font-bold text-foreground mb-2">Alert Center</h1>
              <p className="text-muted-foreground">Manage your real-time market monitoring alerts.</p>
            </div>
            <div className="text-center py-12 text-muted-foreground">
              Alert management interface coming soon...
            </div>
          </div>
        );
      default:
        return <div>Section not found</div>;
    }
  };

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="min-h-screen w-full flex bg-gradient-hero">
        <AppSidebar activeSection={activeSection} onSectionChange={setActiveSection} />
        <div className="flex-1 flex flex-col overflow-hidden">
          <Header />
          <main className="flex-1 overflow-auto p-6 lg:p-8">
            {renderContent()}
          </main>
        </div>
        <AIAssistant />
      </div>
    </SidebarProvider>
  );
};

export default Index;