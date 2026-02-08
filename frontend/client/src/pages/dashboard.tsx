import { useQuery } from "@tanstack/react-query";
import { Link } from "wouter";
import {
  ArrowRight,
  BarChart3,
  DollarSign,
  Package,
  Play,
  Plus,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { Pie, PieChart, Cell, Line, LineChart, CartesianGrid, XAxis, YAxis, Bar, BarChart } from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProviderBadge, RunStatusBadge } from "@/components/run-status-badge";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { formatCurrency, formatRelativeTime, truncateText } from "@/lib/formatters";
import type { DashboardOverview } from "@shared/schema";

const providerColors: Record<string, string> = {
  aws: "hsl(var(--chart-1))",
  gcp: "hsl(var(--chart-2))",
};

function DeltaText({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const positive = value >= 0;
  return (
    <div className={`flex items-center gap-1 text-sm ${positive ? "text-emerald-500" : "text-red-500"}`}>
      {positive ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
      <span>
        {positive ? "+" : ""}
        {value}
        {suffix}
      </span>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery<DashboardOverview>({
    queryKey: ["/api/dashboard/overview?days=30"],
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="page-dashboard">
        <Skeleton className="h-12 w-80" />
        <div className="grid gap-4 md:grid-cols-4">{[...Array(4)].map((_, i) => <Skeleton key={i} className="h-32" />)}</div>
        <div className="grid gap-4 lg:grid-cols-3">{[...Array(3)].map((_, i) => <Skeleton key={i} className="h-40" />)}</div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <Card data-testid="page-dashboard">
        <CardContent className="p-10 text-center">
          <p className="text-sm text-muted-foreground">Unable to load dashboard overview right now.</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-dashboard">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Infrastructure Overview</h1>
          <p className="text-muted-foreground">Monitor and manage your cloud infrastructure</p>
        </div>
        <Link href="/create">
          <Button data-testid="button-create-run-dashboard">
            <Plus className="mr-2 h-4 w-4" />
            New Run
          </Button>
        </Link>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Total Runs</p>
              <Play className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-3xl font-bold">{data.kpis.total_runs}</p>
            <DeltaText value={data.kpis.runs_delta_pct} />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Active Runs</p>
              <Zap className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-3xl font-bold">{data.kpis.active_runs}</p>
            <p className="text-sm text-muted-foreground">Current workflows in progress</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Resources</p>
              <Package className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-3xl font-bold">{data.kpis.resources}</p>
            <DeltaText value={data.kpis.resources_delta} suffix=" this week" />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">Monthly Cost</p>
              <DollarSign className="h-4 w-4 text-primary" />
            </div>
            <p className="mt-2 text-3xl font-bold">{formatCurrency(data.kpis.monthly_cost)}</p>
            <DeltaText value={data.kpis.cost_delta_pct} />
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Link href="/create">
          <Card className="h-full hover-elevate cursor-pointer">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-xl font-semibold">Create New Run</p>
                <p className="text-muted-foreground">Deploy infrastructure with AI</p>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </CardContent>
          </Card>
        </Link>
        <Link href="/runs">
          <Card className="h-full hover-elevate cursor-pointer">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-xl font-semibold">View All Runs</p>
                <p className="text-muted-foreground">Manage running deployments</p>
              </div>
              <ArrowRight className="h-5 w-5 text-muted-foreground" />
            </CardContent>
          </Card>
        </Link>
        <Link href="/analytics">
          <Card className="h-full hover-elevate cursor-pointer">
            <CardContent className="flex items-center justify-between p-6">
              <div>
                <p className="text-xl font-semibold">View Analytics</p>
                <p className="text-muted-foreground">Costs, trends, and insights</p>
              </div>
              <BarChart3 className="h-5 w-5 text-muted-foreground" />
            </CardContent>
          </Card>
        </Link>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Run Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer
              config={{
                runs: { label: "Runs", color: "hsl(var(--chart-1))" },
              }}
              className="h-[280px] w-full"
            >
              <LineChart data={data.run_activity}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickFormatter={(value) => value.slice(5)} />
                <YAxis allowDecimals={false} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Line type="monotone" dataKey="runs" stroke="var(--color-runs)" strokeWidth={2} dot={false} />
              </LineChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Provider Distribution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <ChartContainer
              config={{
                aws: { label: "AWS", color: providerColors.aws },
                gcp: { label: "GCP", color: providerColors.gcp },
              }}
              className="h-[220px] w-full"
            >
              <PieChart>
                <Pie data={data.provider_distribution} dataKey="count" nameKey="provider" innerRadius={60} outerRadius={90}>
                  {data.provider_distribution.map((entry) => (
                    <Cell key={entry.provider} fill={providerColors[entry.provider]} />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent />} />
              </PieChart>
            </ChartContainer>
            <div className="space-y-2">
              {data.provider_distribution.map((item) => (
                <div key={item.provider} className="flex items-center justify-between text-sm">
                  <ProviderBadge provider={item.provider} />
                  <span className="text-muted-foreground">{item.percentage}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Runs</CardTitle>
            <Link href="/runs">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.recent_runs.length === 0 ? (
              <p className="text-sm text-muted-foreground">No runs available yet.</p>
            ) : (
              data.recent_runs.map((run) => (
                <Link href={`/runs/${run.run_id}`} key={run.run_id}>
                  <div className="flex cursor-pointer items-center gap-3 rounded-md border p-3 hover-elevate">
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{truncateText(run.request || run.run_id, 90)}</p>
                      <p className="text-xs text-muted-foreground">
                        {run.created_at ? formatRelativeTime(run.created_at) : "just now"}
                      </p>
                    </div>
                    <ProviderBadge provider={run.provider} />
                    <RunStatusBadge status={run.status} />
                  </div>
                </Link>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Status Overview</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer
              config={{
                count: { label: "Count", color: "hsl(var(--chart-1))" },
              }}
              className="h-[300px] w-full"
            >
              <BarChart data={data.status_overview} layout="vertical" margin={{ left: 16 }}>
                <CartesianGrid horizontal={false} />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="status" width={80} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
