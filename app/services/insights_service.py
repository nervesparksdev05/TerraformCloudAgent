"""
Computed datasets for dashboard, resources, analytics, and monitoring views.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Tuple

from app.core import config
from app.core.database import db


ACTIVE_STATUSES = {"planning", "applying", "destroying", "approved", "reviewing"}
SUCCESS_STATUSES = {"completed", "destroyed"}


def parse_iso(ts: str | None) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _in_days(run: Dict[str, Any], days: int) -> bool:
    created = parse_iso(run.get("created_at"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return created >= cutoff


def _month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def _day_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _safe_percentage(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return round((part / whole) * 100.0, 2)


def _resource_status_from_run_status(status: str) -> str:
    if status in {"failed"}:
        return "error"
    if status in {"destroyed", "destroying"}:
        return "deleted"
    return "active"


def _extract_resource_blocks(tf_text: str) -> List[Tuple[str, str, str]]:
    items: List[Tuple[str, str, str]] = []
    pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', re.MULTILINE)
    for match in pattern.finditer(tf_text):
        resource_type = match.group(1)
        resource_name = match.group(2)
        start = match.end() - 1
        block = _read_brace_block(tf_text, start)
        items.append((resource_type, resource_name, block))
    return items


def _read_brace_block(text: str, brace_start_idx: int) -> str:
    depth = 0
    end = brace_start_idx
    for idx in range(brace_start_idx, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = idx
                break
    return text[brace_start_idx : end + 1]


def _extract_tags(resource_block: str) -> List[str]:
    tags: List[str] = []
    for block_name in ("tags", "labels"):
        match = re.search(rf"{block_name}\s*=\s*\{{(.*?)\}}", resource_block, re.DOTALL)
        if not match:
            continue
        inner = match.group(1)
        for kv in re.findall(r'([A-Za-z0-9_\-\.]+)\s*=\s*"([^"]+)"', inner):
            tags.append(f"{kv[0]}:{kv[1]}")
    return tags


def build_resources_inventory(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    resources: List[Dict[str, Any]] = []
    for run in runs:
        if run.get("status") in {"destroyed", "destroying"}:
            continue

        workspace = Path(run.get("log_path", ""))
        main_tf = workspace / "main.tf"
        if not main_tf.exists():
            continue

        try:
            tf_text = main_tf.read_text(encoding="utf-8")
        except Exception:
            continue

        extracted = _extract_resource_blocks(tf_text)
        if not extracted:
            continue

        per_resource_cost = 0.0
        estimated_cost = _to_float(run.get("estimated_cost"))
        if estimated_cost > 0 and len(extracted) > 0:
            per_resource_cost = estimated_cost / len(extracted)

        for resource_type, resource_name, resource_block in extracted:
            resources.append(
                {
                    "id": f"{run['run_id']}::{resource_type}::{resource_name}",
                    "name": resource_name,
                    "type": resource_type,
                    "provider": run.get("provider", "aws"),
                    "status": _resource_status_from_run_status(run.get("status", "created")),
                    "cost_per_month": round(per_resource_cost, 2),
                    "last_updated": run.get("updated_at") or run.get("created_at"),
                    "tags": _extract_tags(resource_block),
                    "run_id": run["run_id"],
                }
            )

    resources.sort(key=lambda item: parse_iso(item.get("last_updated")), reverse=True)
    return resources


def _status_counts(runs: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for run in runs:
        status = run.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
    return [{"status": key, "count": value} for key, value in sorted(counts.items(), key=lambda i: i[0])]


def _provider_distribution(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {"aws": 0, "gcp": 0}
    for run in runs:
        provider = (run.get("provider") or "aws").lower()
        counts[provider] = counts.get(provider, 0) + 1
    total = max(sum(counts.values()), 1)
    return [
        {
            "provider": provider,
            "count": count,
            "percentage": _safe_percentage(count, total),
        }
        for provider, count in counts.items()
        if count > 0
    ]


def _runs_over_days(runs: List[Dict[str, Any]], days: int) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    buckets: Dict[str, int] = {}
    for idx in range(days):
        day = now - timedelta(days=(days - idx - 1))
        buckets[_day_key(day)] = 0

    for run in runs:
        created = parse_iso(run.get("created_at"))
        key = _day_key(created)
        if key in buckets:
            buckets[key] += 1

    return [{"date": day, "runs": count} for day, count in buckets.items()]


def _cost_trend(runs: List[Dict[str, Any]], months: int = 6) -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    keys: List[str] = []
    for idx in range(months):
        month_dt = (now.replace(day=1) - timedelta(days=idx * 31)).replace(day=1)
        key = _month_key(month_dt)
        if key not in keys:
            keys.append(key)
    keys = sorted(keys)
    values: Dict[str, float] = {key: 0.0 for key in keys}

    for run in runs:
        created = parse_iso(run.get("created_at"))
        key = _month_key(created)
        if key in values and run.get("status") not in {"destroyed", "destroying", "failed"}:
            values[key] += _to_float(run.get("estimated_cost"))

    return [{"month": key, "cost": round(values[key], 2)} for key in keys]


def _compute_delta_percent(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0 if current == 0 else 100.0
    return round(((current - previous) / previous) * 100.0, 2)


def build_dashboard_overview(runs: List[Dict[str, Any]], days: int = 30) -> Dict[str, Any]:
    runs_sorted = sorted(runs, key=lambda item: parse_iso(item.get("created_at")), reverse=True)
    recent = runs_sorted[:7]
    active_runs = [r for r in runs if r.get("status") in ACTIVE_STATUSES]
    resources = build_resources_inventory(runs)

    now = datetime.now(timezone.utc)
    current_month = _month_key(now)
    previous_month = _month_key((now.replace(day=1) - timedelta(days=1)))

    month_counts = {current_month: 0, previous_month: 0}
    month_costs = {current_month: 0.0, previous_month: 0.0}
    for run in runs:
        key = _month_key(parse_iso(run.get("created_at")))
        if key in month_counts:
            month_counts[key] += 1
            if run.get("status") not in {"destroyed", "destroying", "failed"}:
                month_costs[key] += _to_float(run.get("estimated_cost"))

    this_week = [r for r in runs if _in_days(r, 7)]
    prev_week = [r for r in runs if 7 < (datetime.now(timezone.utc) - parse_iso(r.get("created_at"))).days <= 14]
    this_week_resources = sum(int(r.get("resources_add") or 0) for r in this_week)
    prev_week_resources = sum(int(r.get("resources_add") or 0) for r in prev_week)

    monthly_cost = round(sum(item.get("cost_per_month", 0.0) for item in resources), 2)

    return {
        "kpis": {
            "total_runs": len(runs),
            "active_runs": len(active_runs),
            "resources": len(resources),
            "monthly_cost": monthly_cost,
            "runs_delta_pct": _compute_delta_percent(month_counts[current_month], month_counts[previous_month]),
            "resources_delta": this_week_resources - prev_week_resources,
            "cost_delta_pct": _compute_delta_percent(month_costs[current_month], month_costs[previous_month]),
        },
        "run_activity": _runs_over_days(runs, days),
        "provider_distribution": _provider_distribution(runs),
        "recent_runs": recent,
        "status_overview": _status_counts(runs),
    }


def build_resources_payload(
    runs: List[Dict[str, Any]],
    *,
    provider: str = "all",
    resource_type: str = "all",
    search: str = "",
    sort: str = "updated_desc",
) -> Dict[str, Any]:
    items = build_resources_inventory(runs)
    search_lower = (search or "").strip().lower()

    if provider != "all":
        items = [item for item in items if item["provider"] == provider]
    if resource_type != "all":
        items = [item for item in items if item["type"] == resource_type]
    if search_lower:
        items = [
            item
            for item in items
            if search_lower in item["name"].lower()
            or search_lower in item["type"].lower()
            or search_lower in item["run_id"].lower()
        ]

    if sort == "cost_desc":
        items.sort(key=lambda i: float(i.get("cost_per_month") or 0.0), reverse=True)
    elif sort == "cost_asc":
        items.sort(key=lambda i: float(i.get("cost_per_month") or 0.0))
    elif sort == "name_asc":
        items.sort(key=lambda i: i.get("name", ""))
    else:
        items.sort(key=lambda i: parse_iso(i.get("last_updated")), reverse=True)

    available_types = sorted({item["type"] for item in build_resources_inventory(runs)})
    return {
        "items": items,
        "total": len(items),
        "monthly_cost": round(sum(float(item.get("cost_per_month") or 0.0) for item in items), 2),
        "available_types": available_types,
    }


def _parse_range_to_days(range_key: str) -> int:
    mapping = {"7d": 7, "30d": 30, "90d": 90}
    return mapping.get(range_key, 30)


def build_analytics_summary(runs: List[Dict[str, Any]], range_key: str = "30d") -> Dict[str, Any]:
    days = _parse_range_to_days(range_key)
    filtered_runs = [run for run in runs if _in_days(run, days)]

    total = len(filtered_runs)
    success_count = len([r for r in filtered_runs if r.get("status") in SUCCESS_STATUSES])
    failed_count = len([r for r in filtered_runs if r.get("status") == "failed"])
    durations = [int(r.get("duration") or 0) for r in filtered_runs if int(r.get("duration") or 0) > 0]
    avg_duration = round(mean(durations), 2) if durations else 0.0
    total_cost = round(
        sum(_to_float(r.get("estimated_cost")) for r in filtered_runs if r.get("status") not in {"failed", "destroyed"}),
        2,
    )

    return {
        "kpis": {
            "total_runs": total,
            "success_rate": _safe_percentage(success_count, total if total > 0 else 1),
            "avg_duration": avg_duration,
            "failed": failed_count,
            "total_cost": total_cost,
        },
        "runs_over_time": _runs_over_days(filtered_runs, days),
        "cost_trend": _cost_trend(filtered_runs, months=6),
        "status_distribution": _status_counts(filtered_runs),
        "provider_comparison": _provider_distribution(filtered_runs),
    }


def build_monitoring_overview(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    active = [r for r in runs if r.get("status") in ACTIVE_STATUSES]
    recent_failed = [r for r in runs if r.get("status") == "failed"][:5]
    runs_sorted = sorted(runs, key=lambda item: parse_iso(item.get("updated_at") or item.get("created_at")), reverse=True)

    services = [
        {"name": "API Server", "status": "online", "latency_ms": 12},
        {"name": "Database", "status": "online" if db.is_connected else "degraded", "latency_ms": 3 if db.is_connected else 0},
        {"name": "Terraform Engine", "status": "online" if shutil.which("terraform") else "degraded", "latency_ms": 45},
    ]

    errors = []
    for run in recent_failed:
        errors.append(
            {
                "run_id": run["run_id"],
                "message": run.get("error") or "Run failed",
                "created_at": run.get("updated_at") or run.get("created_at"),
            }
        )

    activity_feed = []
    for run in runs_sorted[:20]:
        activity_feed.append(
            {
                "id": f"{run['run_id']}:{run.get('status')}",
                "message": f"Run {run['run_id']} is {run.get('status')}",
                "timestamp": run.get("updated_at") or run.get("created_at"),
                "level": "error" if run.get("status") == "failed" else "info",
            }
        )

    return {
        "services": services,
        "active_runs": {"count": len(active), "items": active[:10]},
        "recent_errors": errors,
        "activity_feed": activity_feed,
    }
