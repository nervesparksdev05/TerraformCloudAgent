"""
Application settings persistence with Mongo + file fallback.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.core import config
from app.core.database import db


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DEFAULT_SETTINGS: Dict[str, Any] = {
    "general": {
        "app_name": "Terraform Agent",
        "auto_refresh_seconds": 10,
    },
    "providers": {
        "default_provider": config.DEFAULT_PROVIDER,
        "default_region_aws": config.AWS_REGION,
        "default_region_gcp": config.GCP_REGION,
    },
    "notifications": {
        "run_completed": True,
        "run_failed": True,
        "approval_required": True,
        "cost_alert": False,
    },
    "security": {
        "require_approval": True,
        "maximum_cost_per_run": 500.0,
    },
    "advanced": {
        "debug_mode": False,
    },
    "updated_at": "",
}


class SettingsStore:
    def __init__(self, file_path: Path | None = None):
        self.file_path = file_path or (config.WORKSPACE_BASE_DIR / "app_settings.json")

    def _ensure_defaults(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = _deep_merge(DEFAULT_SETTINGS, payload)
        data["updated_at"] = payload.get("updated_at") or _now_iso()
        return data

    def _read_file(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return self._ensure_defaults({})
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            return self._ensure_defaults(data if isinstance(data, dict) else {})
        except Exception:
            return self._ensure_defaults({})

    def _write_file(self, payload: Dict[str, Any]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get(self) -> Dict[str, Any]:
        if db.is_connected:
            settings = db.get_settings()
            if settings:
                return self._ensure_defaults(settings)
        return self._read_file()

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        current = self.get()
        merged = _deep_merge(current, patch)
        merged["updated_at"] = _now_iso()
        if db.is_connected:
            db.upsert_settings(merged)
        self._write_file(merged)
        return merged

    def reset(self) -> Dict[str, Any]:
        reset_data = self._ensure_defaults({})
        reset_data["updated_at"] = _now_iso()
        if db.is_connected:
            db.upsert_settings(reset_data)
        self._write_file(reset_data)
        return reset_data


def _deep_merge(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(output.get(key), dict):
            output[key] = _deep_merge(output[key], value)
        else:
            output[key] = value
    return output
