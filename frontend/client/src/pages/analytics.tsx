import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency } from "@/lib/formatters";
import type { AnalyticsSummary } from "@shared/schema";

const providerColors: Record<string, string> = {
  aws: "hsl(var(--chart-1))",
  gcp: "hsl(var(--chart-2))",
};

export default function AnalyticsPage() {
  const [range, setRange] = useState<"7d" | "30d" | "90d">("30d");
  const query = `/api/analytics/summary?range=${range}`;
  const { data, isLoading, isError } = useQuery<AnalyticsSummary>({
    queryKey: [query],
    refetchInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="space-y-4" data-testid="page-analytics">
        <Skeleton className="h-12 w-72" />
        <div className="grid gap-4 md:grid-cols-5">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
        <div className="grid gap-4 lg:grid-cols-2">{[...Array(2)].map((_, i) => <Skeleton key={i} className="h-80" />)}</div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <Card data-testid="page-analytics">
        <CardContent className="p-10 text-center text-sm text-muted-foreground">Unable to load analytics data.</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-analytics">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold tracking-tight">Analytics & Insights</h1>
          <p className="text-muted-foreground">Performance metrics and cost analysis</p>
        </div>
        <Select value={range} onValueChange={(value: "7d" | "30d" | "90d") => setRange(value)}>
          <SelectTrigger className="w-[170px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7d">Last 7 days</SelectItem>
            <SelectItem value="30d">Last 30 days</SelectItem>
            <SelectItem value="90d">Last 90 days</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <Card><CardContent className="p-5"><p className="text-muted-foreground">Total Runs</p><p className="text-3xl font-bold">{data.kpis.total_runs}</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-muted-foreground">Success Rate</p><p className="text-3xl font-bold">{data.kpis.success_rate}%</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-muted-foreground">Avg Duration</p><p className="text-3xl font-bold">{data.kpis.avg_duration}s</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-muted-foreground">Failed</p><p className="text-3xl font-bold">{data.kpis.failed}</p></CardContent></Card>
        <Card><CardContent className="p-5"><p className="text-muted-foreground">Total Cost</p><p className="text-3xl font-bold">{formatCurrency(data.kpis.total_cost)}</p></CardContent></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Runs Over Time</CardTitle></CardHeader>
          <CardContent>
            <ChartContainer config={{ runs: { label: "Runs", color: "hsl(var(--chart-1))" } }} className="h-[300px] w-full">
              <LineChart data={data.runs_over_time}>
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
          <CardHeader><CardTitle>Cost Trend</CardTitle></CardHeader>
          <CardContent>
            <ChartContainer config={{ cost: { label: "Cost", color: "hsl(var(--chart-2))" } }} className="h-[300px] w-full">
              <BarChart data={data.cost_trend}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="month" tickFormatter={(v) => v.slice(5)} />
                <YAxis />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="cost" fill="var(--color-cost)" radius={6} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Status Distribution</CardTitle></CardHeader>
          <CardContent>
            <ChartContainer config={{ count: { label: "Count", color: "hsl(var(--chart-1))" } }} className="h-[300px] w-full">
              <BarChart data={data.status_distribution} layout="vertical" margin={{ left: 16 }}>
                <CartesianGrid horizontal={false} />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="status" width={80} />
                <ChartTooltip content={<ChartTooltipContent />} />
                <Bar dataKey="count" fill="var(--color-count)" radius={4} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Provider Comparison</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <ChartContainer
              config={{
                aws: { label: "AWS", color: providerColors.aws },
                gcp: { label: "GCP", color: providerColors.gcp },
              }}
              className="h-[230px] w-full"
            >
              <PieChart>
                <Pie data={data.provider_comparison} dataKey="count" nameKey="provider" innerRadius={55} outerRadius={88}>
                  {data.provider_comparison.map((entry) => (
                    <Cell key={entry.provider} fill={providerColors[entry.provider]} />
                  ))}
                </Pie>
                <ChartTooltip content={<ChartTooltipContent />} />
              </PieChart>
            </ChartContainer>
            <div className="space-y-2">
              {data.provider_comparison.map((item) => (
                <div key={item.provider} className="flex items-center justify-between text-sm">
                  <span>{item.provider.toUpperCase()}</span>
                  <span className="text-muted-foreground">{item.percentage}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
