import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RunStatusBadge, ProviderBadge } from "@/components/run-status-badge";
import { formatRelativeTime, truncateText } from "@/lib/formatters";
import { Link } from "wouter";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Search, Plus, Filter, Ban, CheckCircle, Trash2, Play, X } from "lucide-react";
import type { Run } from "@shared/schema";

const RUNS_FILTERS_KEY = "terraform-agent-runs-filters";

export default function Runs() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [providerFilter, setProviderFilter] = useState("all");
  const [sortBy, setSortBy] = useState<"newest" | "oldest" | "cost_desc" | "cost_asc">("newest");
  const { toast } = useToast();

  useEffect(() => {
    try {
      const raw = localStorage.getItem(RUNS_FILTERS_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        searchQuery?: string;
        statusFilter?: string;
        providerFilter?: string;
        sortBy?: "newest" | "oldest" | "cost_desc" | "cost_asc";
      };
      if (typeof parsed.searchQuery === "string") setSearchQuery(parsed.searchQuery);
      if (typeof parsed.statusFilter === "string") setStatusFilter(parsed.statusFilter);
      if (typeof parsed.providerFilter === "string") setProviderFilter(parsed.providerFilter);
      if (parsed.sortBy) setSortBy(parsed.sortBy);
    } catch {
      // no-op for invalid local storage payload
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(
      RUNS_FILTERS_KEY,
      JSON.stringify({ searchQuery, statusFilter, providerFilter, sortBy }),
    );
  }, [searchQuery, statusFilter, providerFilter, sortBy]);

  const { data: runs, isLoading } = useQuery<Run[]>({
    queryKey: ["/api/runs"],
    refetchInterval: 5000,
  });

  const approveMutation = useMutation({
    mutationFn: (runId: string) => apiRequest("POST", `/api/runs/${runId}/approve`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Run approved" });
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (runId: string) => apiRequest("POST", `/api/runs/${runId}/reject`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Run rejected" });
    },
  });

  const destroyMutation = useMutation({
    mutationFn: (runId: string) => apiRequest("POST", `/api/runs/${runId}/destroy`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });
      toast({ title: "Destroy started" });
    },
  });

  const filteredRuns = (runs ?? [])
    .filter((run) => {
      if (searchQuery && !((run.request ?? "").toLowerCase().includes(searchQuery.toLowerCase()) || run.run_id.includes(searchQuery))) return false;
      if (statusFilter !== "all" && run.status !== statusFilter) return false;
      if (providerFilter !== "all" && run.provider !== providerFilter) return false;
      return true;
    })
    .sort((a, b) => {
      const aDate = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bDate = b.created_at ? new Date(b.created_at).getTime() : 0;
      const aCost = Number(a.estimated_cost ?? 0);
      const bCost = Number(b.estimated_cost ?? 0);
      if (sortBy === "oldest") return aDate - bDate;
      if (sortBy === "cost_desc") return bCost - aCost;
      if (sortBy === "cost_asc") return aCost - bCost;
      return bDate - aDate;
    });

  const hasActiveFilters =
    statusFilter !== "all" || providerFilter !== "all" || searchQuery.length > 0 || sortBy !== "newest";

  return (
    <div className="space-y-5 animate-fade-in" data-testid="page-runs">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">All Runs</h1>
          <p className="text-sm text-muted-foreground">{filteredRuns.length} runs found</p>
        </div>
        <Link href="/create">
          <Button data-testid="button-create-run">
            <Plus className="h-4 w-4 mr-2" />
            Create Run
          </Button>
        </Link>
      </div>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[200px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search by request or run ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            data-testid="input-search-runs"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-[160px]" data-testid="select-status-filter">
            <Filter className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="created">Created</SelectItem>
            <SelectItem value="planning">Planning</SelectItem>
            <SelectItem value="planned">Planned</SelectItem>
            <SelectItem value="reviewing">Reviewing</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="applying">Applying</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="destroying">Destroying</SelectItem>
            <SelectItem value="destroyed">Destroyed</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
        <Select value={providerFilter} onValueChange={setProviderFilter}>
          <SelectTrigger className="w-[130px]" data-testid="select-provider-filter">
            <SelectValue placeholder="Provider" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Providers</SelectItem>
            <SelectItem value="aws">AWS</SelectItem>
            <SelectItem value="gcp">GCP</SelectItem>
          </SelectContent>
        </Select>
        <Select value={sortBy} onValueChange={(value: "newest" | "oldest" | "cost_desc" | "cost_asc") => setSortBy(value)}>
          <SelectTrigger className="w-[140px]" data-testid="select-runs-sort">
            <SelectValue placeholder="Sort" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="newest">Newest</SelectItem>
            <SelectItem value="oldest">Oldest</SelectItem>
            <SelectItem value="cost_desc">Highest Cost</SelectItem>
            <SelectItem value="cost_asc">Lowest Cost</SelectItem>
          </SelectContent>
        </Select>
        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSearchQuery("");
              setStatusFilter("all");
              setProviderFilter("all");
              setSortBy("newest");
            }}
            data-testid="button-clear-filters"
          >
            <X className="h-3.5 w-3.5 mr-1" />
            Clear
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-20 w-full rounded-md" />)}
        </div>
      ) : filteredRuns.length > 0 ? (
        <div className="space-y-2">
          {filteredRuns.map((run) => (
            <Card key={run.run_id} className="hover-elevate" data-testid={`card-run-${run.run_id}`}>
              <CardContent className="p-4">
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex-1 min-w-0">
                    <Link href={`/runs/${run.run_id}`}>
                      <p className="text-sm font-medium hover:underline cursor-pointer truncate" data-testid={`link-run-${run.run_id}`}>
                        {truncateText(run.request ?? run.run_id, 80)}
                      </p>
                    </Link>
                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      <span className="text-xs text-muted-foreground font-mono">{run.run_id.slice(0, 12)}</span>
                      <span className="text-xs text-muted-foreground">{run.created_at ? formatRelativeTime(run.created_at) : "just now"}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <ProviderBadge provider={run.provider} />
                    <RunStatusBadge status={run.status} />
                    {run.status === "planned" || run.status === "reviewing" ? (
                      <Button size="sm" variant="outline" onClick={() => approveMutation.mutate(run.run_id)}>
                        <CheckCircle className="h-4 w-4 mr-1" /> Approve
                      </Button>
                    ) : null}
                    {!["completed", "failed", "destroyed"].includes(run.status) ? (
                      <Button size="sm" variant="outline" onClick={() => rejectMutation.mutate(run.run_id)}>
                        <Ban className="h-4 w-4 mr-1" /> Reject
                      </Button>
                    ) : null}
                    {run.status === "completed" ? (
                      <Button size="sm" variant="destructive" onClick={() => destroyMutation.mutate(run.run_id)}>
                        <Trash2 className="h-4 w-4 mr-1" /> Destroy
                      </Button>
                    ) : null}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Play className="h-12 w-12 text-muted-foreground/30 mb-4" />
            <h3 className="text-lg font-semibold mb-1">No runs found</h3>
            <p className="text-sm text-muted-foreground mb-4">
              {hasActiveFilters ? "Try adjusting your filters" : "Create your first infrastructure run"}
            </p>
            {!hasActiveFilters && (
              <Link href="/create">
                <Button data-testid="button-create-first-run-empty">
                  <Plus className="h-4 w-4 mr-2" />
                  Create Run
                </Button>
              </Link>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
