import {
  BarChart3,
  Home,
  Search,
  Shield,
  Bell,
  Target,
  Zap,
  MessageCircle,
} from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  useSidebar,
} from "@/components/ui/sidebar";

const navigationItems = [
  { id: "dashboard", name: "Dashboard", icon: Home, path: "/dashboard" },
  { id: "analysis", name: "Feature Analysis", icon: Search, path: "/analysis" },
  { id: "monitoring", name: "Market Monitoring", icon: Shield, path: "/monitoring" },
  { id: "demand", name: "Demand Dashboard", icon: Target, path: "/demand" },
  { id: "battlecards", name: "Battle Cards", icon: Zap, path: "/battlecards" },
  // { id: "alerts", name: "Alerts", icon: Bell, path: "/alerts", badge: "3" },
];

export function AppSidebar() {
  const { open } = useSidebar();
  const location = useLocation();

  return (
    <Sidebar className="border-r border-border/50">
      <SidebarContent className="bg-gradient-card">
        {/* Logo */}
        <div className="p-6 border-b border-border/30">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-primary flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-primary-foreground" />
            </div>
            {open && <span className="font-bold text-xl text-foreground">OneLens</span>}
          </div>
        </div>

        {/* Navigation */}
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navigationItems.map((item) => {
                const Icon = item.icon;

                return (
                  <SidebarMenuItem key={item.id}>
                    <NavLink to={item.path} className="w-full">
                      {({ isActive }) => (
                        <SidebarMenuButton
                          className={`w-full justify-start h-12 ${isActive
                            ? "bg-accent/50 text-accent-foreground border-l-2 border-primary"
                            : ""
                            }`}
                        >
                          <Icon className="w-5 h-5" />
                          {open && (
                            <>
                              <span className="flex-1 text-left">{item.name}</span>
                              {item.badge && (
                                <span className="bg-primary text-primary-foreground text-xs px-2 py-1 rounded-full">
                                  {item.badge}
                                </span>
                              )}
                            </>
                          )}
                        </SidebarMenuButton>
                      )}
                    </NavLink>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {/* User */}
        {open && (
          <div className="mt-auto p-4 border-t border-border/30">
            <div className="flex items-center space-x-3 p-3 rounded-lg bg-muted/30">
              <div className="w-8 h-8 rounded-full bg-gradient-primary" />
              <div className="flex-1">
                <p className="text-sm font-medium text-foreground">John Analyst</p>
                <p className="text-xs text-muted-foreground">Premium Plan</p>
              </div>
            </div>
          </div>
        )}
      </SidebarContent>
    </Sidebar>
  );
}
