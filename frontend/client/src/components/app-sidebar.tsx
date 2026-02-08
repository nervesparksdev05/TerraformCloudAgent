import { useLocation, Link } from "wouter";
import {
  Activity,
  BarChart3,
  LayoutDashboard,
  Package,
  Play,
  Plus,
  Settings,
  Terminal,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarHeader,
  SidebarFooter,
} from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";
import { useQuery } from "@tanstack/react-query";
import type { Run } from "@shared/schema";

const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Runs", url: "/runs", icon: Play },
  { title: "Create Run", url: "/create", icon: Plus },
  { title: "Resources", url: "/resources", icon: Package },
  { title: "Analytics", url: "/analytics", icon: BarChart3 },
  { title: "Monitoring", url: "/monitoring", icon: Activity },
  { title: "Settings", url: "/settings", icon: Settings },
];

export function AppSidebar() {
  const [location] = useLocation();

  const { data: runs } = useQuery<Run[]>({
    queryKey: ["/api/runs"],
    refetchInterval: 10000,
  });

  const activeRunsCount =
    runs?.filter((r) => ["planning", "applying", "destroying"].includes(r.status)).length ?? 0;

  return (
    <Sidebar>
      <SidebarHeader className="p-4">
        <Link href="/" className="flex items-center gap-2" data-testid="link-logo">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Terminal className="h-4 w-4 text-primary-foreground" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-semibold tracking-tight">Terraform Agent</span>
            <span className="text-xs text-muted-foreground">Cloud Infrastructure</span>
          </div>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => {
                const isActive = item.url === "/" ? location === "/" : location.startsWith(item.url);
                return (
                  <SidebarMenuItem key={item.title}>
                    <SidebarMenuButton asChild isActive={isActive}>
                      <Link href={item.url} data-testid={`link-nav-${item.title.toLowerCase().replace(/\s+/g, "-")}`}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.title}</span>
                        {item.title === "Runs" && activeRunsCount > 0 && (
                          <Badge variant="default" className="ml-auto text-xs h-5 min-w-5 flex items-center justify-center">
                            {activeRunsCount}
                          </Badge>
                        )}
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <div className="h-2 w-2 rounded-full bg-emerald-500" />
          <span>System Online</span>
          <span className="ml-auto">v1.0.0</span>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
