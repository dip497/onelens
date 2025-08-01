import { Outlet, useLocation } from "react-router-dom";
import { SidebarProvider } from "../ui/sidebar";
import { AppSidebar } from "./AppSidebar";
import { Header } from "./Header";
import { AIAssistant } from "../ai/AIAssistant";


export default function AppLayout() {
    const location = useLocation();
    const path = location.pathname.split("/")[1] || "dashboard";

    return (
        <SidebarProvider defaultOpen={true}>
            <div className="min-h-screen w-full flex bg-gradient-hero">
                <AppSidebar activeSection={path} onSectionChange={() => { }} />
                <div className="flex-1 flex flex-col overflow-hidden">
                    <Header />
                    <main className="flex-1 overflow-auto p-6 lg:p-8">
                        <Outlet />
                    </main>
                </div>
                <AIAssistant />
            </div>
        </SidebarProvider>
    );
}
