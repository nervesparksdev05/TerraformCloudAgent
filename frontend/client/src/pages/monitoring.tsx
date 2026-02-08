import { useQuery } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime, truncateText } from "@/lib/formatters";
import { ProviderBadge, RunStatusBadge } from "@/components/run-status-badge";
import type { MonitoringOverview } from "@shared/schema";

function serviceStatusClass(status: "online" | "degraded" | "offline") {
  if (status === "online") return "bg-emerald-500";
  if (status === "degraded") return "bg-amber-500";
  return "bg-red-500";
}

export default function MonitoringPage() {
  const { data, isLoading, isError } = useQuery<MonitoringOverview>({
    queryKey: ["/api/monitoring/overview"],
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="page-monitoring">
        <Skeleton className="h-12 w-72" />
        <div className="grid gap-4 md:grid-cols-3">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-28" />)}</div>
        <div className="grid gap-4 lg:grid-cols-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-64" />)}</div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <Card data-testid="page-monitoring">
        <CardContent className="p-10 text-center text-sm text-muted-foreground">Failed to load monitoring data.</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-monitoring">
      <div>
        <h1 className="text-4xl font-bold tracking-tight">Live Monitoring</h1>
        <p className="text-muted-foreground">Real-time system status and activity</p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {data.services.map((service) => (
          <Card key={service.name}>
            <CardContent className="p-5">
              <div className="mb-2 flex items-center gap-2">
                <div className={`h-2.5 w-2.5 rounded-full ${serviceStatusClass(service.status)}`} />
                <p className="text-xl font-semibold">{service.name}</p>
              </div>
              <p className="text-sm text-muted-foreground">
                {service.status === "online" ? "Online" : service.status === "degraded" ? "Degraded" : "Offline"} -{" "}
                {service.latency_ms}ms
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Active Runs</CardTitle>
            <Badge variant="secondary">{data.active_runs.count} active</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.active_runs.items.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <CheckCircle2 className="mb-3 h-12 w-12 text-muted-foreground/30" />
                <p className="text-xl font-medium">No active runs</p>
                <p className="text-muted-foreground">All systems idle</p>
              </div>
            ) : (
              data.active_runs.items.map((run) => (
                <div key={run.run_id} className="flex items-center gap-3 rounded-md border p-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{truncateText(run.request || run.run_id, 80)}</p>
                    <p className="text-xs text-muted-foreground">
                      {run.created_at ? formatRelativeTime(run.created_at) : "just now"}
                    </p>
                  </div>
                  <ProviderBadge provider={run.provider} />
                  <RunStatusBadge status={run.status} />
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Errors</CardTitle>
            <Badge variant="destructive">{data.recent_errors.length}</Badge>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.recent_errors.length === 0 ? (
              <p className="text-sm text-muted-foreground">No recent errors.</p>
            ) : (
              data.recent_errors.map((error) => (
                <div key={error.run_id} className="rounded-md border border-red-500/30 bg-red-500/10 p-3">
                  <div className="mb-1 flex items-start gap-2">
                    <AlertCircle className="mt-0.5 h-4 w-4 text-red-500" />
                    <p className="text-sm font-medium">{truncateText(error.message, 120)}</p>
                  </div>
                  <p className="text-xs text-muted-foreground">{formatRelativeTime(error.created_at)}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Activity Feed</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {data.activity_feed.length === 0 ? (
            <p className="text-sm text-muted-foreground">No activity available.</p>
          ) : (
            data.activity_feed.map((item) => (
              <div key={item.id} className="flex items-start gap-3 rounded-md border p-3">
                <div className={`mt-1 h-2.5 w-2.5 rounded-full ${item.level === "error" ? "bg-red-500" : "bg-blue-500"}`} />
                <div className="flex-1">
                  <p className="text-sm">{item.message}</p>
                  <p className="text-xs text-muted-foreground">{formatRelativeTime(item.timestamp)}</p>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
