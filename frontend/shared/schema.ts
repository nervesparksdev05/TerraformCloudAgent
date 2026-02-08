export type RunStatus =
  | "created"
  | "planning"
  | "planned"
  | "cost_estimated"
  | "reviewing"
  | "approved"
  | "applying"
  | "completed"
  | "destroying"
  | "destroyed"
  | "failed";

export type Provider = "aws" | "gcp";

export interface Run {
  run_id: string;
  status: RunStatus;
  provider: Provider;
  log_path: string;
  request?: string | null;
  region?: string | null;
  method?: string | null;
  template_id?: string | null;
  template_name?: string | null;
  plan_output?: string | null;
  cost_estimate?: Record<string, unknown> | null;
  estimated_cost?: number | null;
  resources_add?: number | null;
  resources_change?: number | null;
  resources_destroy?: number | null;
  duration?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  outputs?: Record<string, unknown> | null;
  error?: string | null;
}

export interface CreateRunPayload {
  request?: string;
  provider: Provider;
  region?: string;
  method?: "natural_language" | "template";
  template_id?: string;
  template_inputs?: Record<string, unknown>;
  auto_approve?: boolean;
}

export interface ChatResponse {
  response: string;
  timestamp: string;
}

export interface TemplateParameter {
  name: string;
  label: string;
  type: "select" | "number" | "text" | "boolean";
  required: boolean;
  default?: any;
  options?: Array<{ value: string; label: string }>;
  min?: number;
  max?: number;
  description?: string;
}

export interface TemplateDefinition {
  id: string;
  name: string;
  description: string;
  category: string;
  providers: Provider[];
  chips: string[];
  parameters?: TemplateParameter[];
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface ProviderDistributionItem {
  provider: Provider;
  count: number;
  percentage: number;
}

export interface DashboardOverview {
  kpis: {
    total_runs: number;
    active_runs: number;
    resources: number;
    monthly_cost: number;
    runs_delta_pct: number;
    resources_delta: number;
    cost_delta_pct: number;
  };
  run_activity: Array<{ date: string; runs: number }>;
  provider_distribution: ProviderDistributionItem[];
  recent_runs: Run[];
  status_overview: StatusCount[];
}

export interface ResourceItem {
  id: string;
  name: string;
  type: string;
  provider: Provider;
  status: "active" | "error" | "deleted";
  cost_per_month: number;
  last_updated: string;
  tags: string[];
  run_id: string;
}

export interface ResourcesResponse {
  items: ResourceItem[];
  total: number;
  monthly_cost: number;
  available_types: string[];
  view: "list" | "grid";
}

export interface AnalyticsSummary {
  kpis: {
    total_runs: number;
    success_rate: number;
    avg_duration: number;
    failed: number;
    total_cost: number;
  };
  runs_over_time: Array<{ date: string; runs: number }>;
  cost_trend: Array<{ month: string; cost: number }>;
  status_distribution: StatusCount[];
  provider_comparison: ProviderDistributionItem[];
}

export interface MonitoringOverview {
  services: Array<{
    name: string;
    status: "online" | "degraded" | "offline";
    latency_ms: number;
  }>;
  active_runs: {
    count: number;
    items: Run[];
  };
  recent_errors: Array<{
    run_id: string;
    message: string;
    created_at: string;
  }>;
  activity_feed: Array<{
    id: string;
    message: string;
    timestamp: string;
    level: "info" | "error";
  }>;
}

export interface AppSettings {
  general: {
    app_name: string;
    auto_refresh_seconds: number;
  };
  providers: {
    default_provider: Provider;
    default_region_aws: string;
    default_region_gcp: string;
  };
  notifications: {
    run_completed: boolean;
    run_failed: boolean;
    approval_required: boolean;
    cost_alert: boolean;
  };
  security: {
    require_approval: boolean;
    maximum_cost_per_run: number;
  };
  advanced: {
    debug_mode: boolean;
  };
  updated_at: string;
}

export interface AdminActionResponse {
  ok: boolean;
  runs_deleted_db: number;
  chat_messages_deleted_db: number;
  workspaces_deleted: number;
  settings_updated_at?: string;
}
