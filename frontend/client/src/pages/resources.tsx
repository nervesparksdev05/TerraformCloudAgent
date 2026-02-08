import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Grid3X3, List, Search } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCurrency, formatRelativeTime } from "@/lib/formatters";
import type { ResourceItem, ResourcesResponse } from "@shared/schema";

const STORAGE_KEY = "terraform-agent-resources-filters";

function statusClass(status: ResourceItem["status"]) {
  if (status === "active") return "bg-emerald-500/15 text-emerald-500 border-emerald-500/30";
  if (status === "error") return "bg-red-500/15 text-red-500 border-red-500/30";
  return "bg-muted text-muted-foreground";
}

export default function ResourcesPage() {
  const [provider, setProvider] = useState<"all" | "aws" | "gcp">("all");
  const [resourceType, setResourceType] = useState("all");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("updated_desc");
  const [view, setView] = useState<"list" | "grid">("list");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        provider?: "all" | "aws" | "gcp";
        resourceType?: string;
        search?: string;
        sort?: string;
        view?: "list" | "grid";
      };
      if (parsed.provider) setProvider(parsed.provider);
      if (parsed.resourceType) setResourceType(parsed.resourceType);
      if (typeof parsed.search === "string") setSearch(parsed.search);
      if (typeof parsed.sort === "string") setSort(parsed.sort);
      if (parsed.view) setView(parsed.view);
    } catch {
      // ignore malformed persisted state
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ provider, resourceType, search, sort, view }));
  }, [provider, resourceType, search, sort, view]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams({
      provider,
      type: resourceType,
      search,
      sort,
      view,
    });
    return `/api/resources?${params.toString()}`;
  }, [provider, resourceType, search, sort, view]);

  const { data, isLoading, isError } = useQuery<ResourcesResponse>({
    queryKey: [queryString],
    refetchInterval: 30000,
  });

  return (
    <div className="space-y-6 animate-fade-in" data-testid="page-resources">
      <div>
        <h1 className="text-4xl font-bold tracking-tight">Infrastructure Resources</h1>
        <p className="text-muted-foreground">
          {data ? `${data.total} resources (${formatCurrency(data.monthly_cost)}/mo)` : "Loading resources..."}
        </p>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {(["all", "aws", "gcp"] as const).map((item) => (
            <Button
              key={item}
              variant={provider === item ? "default" : "outline"}
              size="sm"
              onClick={() => setProvider(item)}
            >
              {item.toUpperCase()}
            </Button>
          ))}
          <div className="ml-auto flex gap-2">
            <Button variant={view === "list" ? "default" : "outline"} size="icon" onClick={() => setView("list")}>
              <List className="h-4 w-4" />
            </Button>
            <Button variant={view === "grid" ? "default" : "outline"} size="icon" onClick={() => setView("grid")}>
              <Grid3X3 className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-3">
          <div className="relative md:col-span-2">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search resources..."
              className="pl-9"
            />
          </div>
          <div className="flex gap-2">
            <Select value={resourceType} onValueChange={setResourceType}>
              <SelectTrigger>
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {(data?.available_types ?? []).map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="w-[170px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="updated_desc">Newest</SelectItem>
                <SelectItem value="name_asc">Name</SelectItem>
                <SelectItem value="cost_desc">Cost High</SelectItem>
                <SelectItem value="cost_asc">Cost Low</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}</div>
      ) : isError || !data ? (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted-foreground">Failed to load resources.</CardContent>
        </Card>
      ) : data.items.length === 0 ? (
        <Card>
          <CardContent className="p-10 text-center text-sm text-muted-foreground">
            No resources found for the selected filters.
          </CardContent>
        </Card>
      ) : view === "list" ? (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y">
              {data.items.map((item) => (
                <div key={item.id} className="flex flex-wrap items-center gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-lg font-semibold">{item.name}</p>
                    <p className="text-sm text-muted-foreground">{item.type}</p>
                  </div>
                  <Badge variant="outline">{item.provider.toUpperCase()}</Badge>
                  <Badge variant="outline" className={statusClass(item.status)}>
                    {item.status}
                  </Badge>
                  <p className="min-w-[100px] text-right text-sm">{formatCurrency(item.cost_per_month)}/mo</p>
                  <p className="min-w-[130px] text-right text-sm text-muted-foreground">
                    {formatRelativeTime(item.last_updated)}
                  </p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {data.items.map((item) => (
            <Card key={item.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-xl">{item.name}</CardTitle>
                <p className="text-sm text-muted-foreground">{item.type}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">{item.provider.toUpperCase()}</Badge>
                  <Badge variant="outline" className={statusClass(item.status)}>
                    {item.status}
                  </Badge>
                </div>
                <p className="text-sm">{formatCurrency(item.cost_per_month)}/mo</p>
                <p className="text-xs text-muted-foreground">{formatRelativeTime(item.last_updated)}</p>
                <div className="flex flex-wrap gap-1">
                  {item.tags.slice(0, 3).map((tag) => (
                    <Badge key={tag} variant="secondary">
                      {tag}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
