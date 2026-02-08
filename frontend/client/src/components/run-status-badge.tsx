import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Circle, Loader2, CheckCircle2, XCircle, Clock,
  Eye, Shield, Trash2, Ban, Zap
} from "lucide-react";

const statusConfig: Record<string, {
  label: string;
  variant: "default" | "secondary" | "destructive" | "outline";
  className: string;
  icon: React.ElementType;
  animated?: boolean;
}> = {
  created: {
    label: "Created",
    variant: "secondary",
    className: "bg-muted text-muted-foreground",
    icon: Circle,
  },
  planning: {
    label: "Planning",
    variant: "default",
    className: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/20",
    icon: Loader2,
    animated: true,
  },
  planned: {
    label: "Planned",
    variant: "default",
    className: "bg-violet-500/15 text-violet-700 dark:text-violet-400 border-violet-500/20",
    icon: Eye,
  },
  reviewing: {
    label: "Reviewing",
    variant: "default",
    className: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/20",
    icon: Clock,
  },
  approved: {
    label: "Approved",
    variant: "default",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
    icon: Shield,
  },
  applying: {
    label: "Applying",
    variant: "default",
    className: "bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/20",
    icon: Zap,
    animated: true,
  },
  completed: {
    label: "Completed",
    variant: "default",
    className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/20",
    icon: CheckCircle2,
  },
  destroying: {
    label: "Destroying",
    variant: "default",
    className: "bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/20",
    icon: Trash2,
    animated: true,
  },
  destroyed: {
    label: "Destroyed",
    variant: "secondary",
    className: "bg-muted text-muted-foreground",
    icon: Trash2,
  },
  failed: {
    label: "Failed",
    variant: "destructive",
    className: "bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/20",
    icon: XCircle,
  },
  cancelled: {
    label: "Cancelled",
    variant: "secondary",
    className: "bg-muted text-muted-foreground",
    icon: Ban,
  },
};

export function RunStatusBadge({ status, size = "sm" }: { status: string; size?: "sm" | "default" }) {
  const config = statusConfig[status] || statusConfig.created;
  const Icon = config.icon;

  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 border font-medium",
        config.className,
        size === "sm" && "text-xs"
      )}
      data-testid={`badge-status-${status}`}
    >
      <Icon className={cn("h-3 w-3", config.animated && "animate-spin")} />
      {config.label}
    </Badge>
  );
}

export function ProviderBadge({ provider }: { provider: string }) {
  const isAWS = provider.toLowerCase() === "aws";
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 border font-medium text-xs",
        isAWS
          ? "bg-orange-500/10 text-orange-700 dark:text-orange-400 border-orange-500/20"
          : "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20"
      )}
      data-testid={`badge-provider-${provider}`}
    >
      {isAWS ? "AWS" : "GCP"}
    </Badge>
  );
}
