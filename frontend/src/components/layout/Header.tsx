import { SidebarTrigger } from "@/components/ui/sidebar";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useNavigate } from "react-router-dom";

export function Header() {
  const navigate = useNavigate();

  const handleAdminClick = () => navigate("/admin");
  const handleProfileClick = () => navigate("/profile");
  const handleLogoutClick = () => {
    // Perform logout logic here
    // e.g., clear tokens, reset state, redirect to login
    localStorage.clear();
    navigate("/login");
  };

  return (
    <header className="h-14 border-b border-border/50 bg-background/80 backdrop-blur-md sticky top-0 z-50">
      <div className="flex items-center justify-between h-full px-4">
        <div className="flex items-center space-x-3">
          <SidebarTrigger className="h-8 w-8" />
          <div className="text-sm text-muted-foreground">
            Product Intelligence Platform
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <ThemeToggle />

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <div className="flex items-center space-x-2 text-sm cursor-pointer">
                <div className="w-6 h-6 rounded-full bg-gradient-primary" />
                <span className="text-foreground font-medium">
                  John Analyst
                </span>
              </div>
            </DropdownMenuTrigger>

            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={handleProfileClick}>
                Profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleAdminClick}>
                Admin Section
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleLogoutClick}>
                Logout
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
