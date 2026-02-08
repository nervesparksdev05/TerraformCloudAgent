"""
FastAPI application entrypoint.
"""
from __future__ import annotations

import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query

from app.core import config
from app.core.database import db
from app.core.logger import get_logger, setup_logging
from app.models.schemas import (
    AdminConfirmRequest,
    AgentRequest,
    ChatRequest,
    ChatResponse,
    RunResponse,
    SettingsUpdateRequest,
    TerraformBundle,
)
from app.services.insights_service import (
    build_analytics_summary,
    build_dashboard_overview,
    build_monitoring_overview,
    build_resources_payload,
)
from app.services.llm_generator import LLMGenerator
from app.services.security_checker import SecurityChecker
from app.services.settings_store import SettingsStore
from app.services.templates_catalog import (
    AWS_REGIONS,
    GCP_REGIONS,
    compose_template_request,
    get_template_catalog,
    get_templates_by_category,
)
from app.services.terraform_runner import TerraformRunner
from app.services.workspace_manager import WorkspaceManager

setup_logging(log_dir=config.LOGS_DIR, log_level="DEBUG" if config.DEBUG else "INFO")
logger = get_logger(__name__)

app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION,
    docs_url="/docs",
)

workspace_manager = WorkspaceManager(base_dir=str(config.WORKSPACE_BASE_DIR))
settings_store = SettingsStore()
try:
    llm_generator = LLMGenerator()
except Exception as exc:
    llm_generator = None
    logger.warning(f"LLM generator unavailable at startup, mock fallback will be used: {exc}")


def _is_mock_run(run: Dict[str, Any]) -> bool:
    cost_estimate = run.get("cost_estimate")
    return isinstance(cost_estimate, dict) and cost_estimate.get("mode") == "mock"


def _build_mock_bundle(provider: str, request: str, feedback: Optional[str] = None) -> TerraformBundle:
    if provider == "gcp":
        main_tf = """
terraform {
  required_version = ">= 1.3.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

resource "google_compute_network" "main" {
  name                    = "mock-network"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "main" {
  name          = "mock-subnet"
  ip_cidr_range = "10.10.1.0/24"
  region        = var.region
  network       = google_compute_network.main.id
}
""".strip()
        variables_tf = """
variable "project_id" {
  type    = string
  default = "mock-project-id"
}

variable "region" {
  type    = string
  default = "us-central1"
}
""".strip()
        outputs_tf = f"""
output "network_id" {{
  value = google_compute_network.main.id
}}

output "subnetwork_id" {{
  value = google_compute_subnetwork.main.id
}}

output "mock_request" {{
  value = {json.dumps(request)}
}}

output "mock_feedback" {{
  value = {json.dumps(feedback or "")}
}}
""".strip()
    else:
        main_tf = """
terraform {
  required_version = ">= 1.3.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "mock-vpc"
  }
}

resource "aws_subnet" "main" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = var.availability_zone
  tags = {
    Name = "mock-subnet"
  }
}
""".strip()
        variables_tf = """
variable "region" {
  type    = string
  default = "us-east-1"
}

variable "availability_zone" {
  type    = string
  default = "us-east-1a"
}
""".strip()
        outputs_tf = f"""
output "vpc_id" {{
  value = aws_vpc.main.id
}}

output "subnet_id" {{
  value = aws_subnet.main.id
}}

output "mock_request" {{
  value = {json.dumps(request)}
}}

output "mock_feedback" {{
  value = {json.dumps(feedback or "")}
}}
""".strip()

    return TerraformBundle(main_tf=main_tf, variables_tf=variables_tf, outputs_tf=outputs_tf)


def _generate_bundle_with_fallback(request_text: str, provider: str) -> tuple[TerraformBundle, Optional[str]]:
    if llm_generator is None:
        return _build_mock_bundle(provider, request_text), "LLM generator unavailable"
    try:
        return llm_generator.generate_terraform(request_text, provider=provider), None
    except Exception as exc:
        logger.warning(f"LLM generation failed, using mock bundle: {exc}")
        return _build_mock_bundle(provider, request_text), str(exc)


def _refine_bundle_with_fallback(
    base_request: str,
    current_code: Dict[str, Any],
    feedback: str,
    provider: str,
) -> tuple[TerraformBundle, Optional[str]]:
    if llm_generator is None:
        return _build_mock_bundle(provider, base_request, feedback), "LLM generator unavailable"
    try:
        return (
            llm_generator.refine_terraform(
                base_request=base_request,
                current_code=current_code,
                feedback=feedback,
                provider=provider,
            ),
            None,
        )
    except Exception as exc:
        logger.warning(f"LLM refinement failed, using mock bundle: {exc}")
        return _build_mock_bundle(provider, base_request, feedback), str(exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_or_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return value


def _normalize_run(run_data: Dict[str, Any]) -> Dict[str, Any]:
    run = {k: _iso_or_value(v) for k, v in dict(run_data).items()}
    run_id = run.get("run_id")
    fallback_path = (config.WORKSPACE_BASE_DIR / run_id).resolve() if run_id else config.WORKSPACE_BASE_DIR.resolve()
    run["log_path"] = str(Path(run.get("log_path") or fallback_path).resolve())
    run.setdefault("method", "natural_language")
    run.setdefault("template_id", None)
    run.setdefault("template_name", None)
    run.setdefault("resources_add", 0)
    run.setdefault("resources_change", 0)
    run.setdefault("resources_destroy", 0)
    run.setdefault("plan_output", None)
    run.setdefault("cost_estimate", None)
    run.setdefault("estimated_cost", None)
    run.setdefault("outputs", None)
    run.setdefault("error", None)
    run.setdefault("duration", None)
    run.setdefault("created_at", _now_iso())
    run.setdefault("updated_at", run["created_at"])
    return run


def _state_file_for_run(run: Dict[str, Any]) -> Path:
    return Path(run["log_path"]) / "state.json"


def _write_state_file(run: Dict[str, Any]) -> None:
    state_path = _state_file_for_run(run)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(run, indent=2), encoding="utf-8")


def _read_state_file(run_id: str) -> Optional[Dict[str, Any]]:
    state_path = (config.WORKSPACE_BASE_DIR / run_id / "state.json").resolve()
    if not state_path.exists():
        return None
    try:
        return _normalize_run(json.loads(state_path.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning(f"Failed to read state file for {run_id}: {exc}")
        return None


def _save_run(run_data: Dict[str, Any], *, is_new: bool = False) -> Dict[str, Any]:
    run = _normalize_run(run_data)
    run["updated_at"] = _now_iso()
    run.setdefault("created_at", run["updated_at"])

    if db.is_connected:
        payload = dict(run)
        if is_new:
            inserted = db.insert_run(payload)
            if not inserted:
                db.update_run(run["run_id"], payload)
        else:
            updated = db.update_run(run["run_id"], payload)
            if not updated:
                db.insert_run(payload)

    _write_state_file(run)
    return run


def _load_terraform_files(run_id: str) -> Optional[Dict[str, str]]:
    """Load Terraform files from workspace directory"""
    workspace_dir = config.WORKSPACE_BASE_DIR / run_id
    if not workspace_dir.exists():
        return None
    
    terraform_code = {}
    
    # Load main.tf
    main_tf_path = workspace_dir / "main.tf"
    if main_tf_path.exists():
        try:
            terraform_code["main_tf"] = main_tf_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read main.tf for {run_id}: {e}")
    
    # Load variables.tf
    variables_tf_path = workspace_dir / "variables.tf"
    if variables_tf_path.exists():
        try:
            terraform_code["variables_tf"] = variables_tf_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read variables.tf for {run_id}: {e}")
    
    # Load outputs.tf
    outputs_tf_path = workspace_dir / "outputs.tf"
    if outputs_tf_path.exists():
        try:
            terraform_code["outputs_tf"] = outputs_tf_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read outputs.tf for {run_id}: {e}")
    
    return terraform_code if terraform_code else None


def _load_run(run_id: str) -> Optional[Dict[str, Any]]:
    run = None
    if db.is_connected:
        mongo_run = db.get_run(run_id)
        if mongo_run:
            run = _normalize_run(mongo_run)
    
    if not run:
        run = _read_state_file(run_id)
    
    # Load Terraform files if run exists
    if run:
        terraform_code = _load_terraform_files(run_id)
        if terraform_code:
            run["terraform_code"] = terraform_code
    
    return run


def _load_run_or_404(run_id: str) -> Dict[str, Any]:
    run = _load_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return run


def _parse_iso(ts: Optional[str]) -> datetime:
    if not ts:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _list_runs() -> List[Dict[str, Any]]:
    items_by_id: Dict[str, Dict[str, Any]] = {}

    if db.is_connected:
        for item in db.list_runs(limit=1000):
            run = _normalize_run(item)
            items_by_id[run["run_id"]] = run

    for state_path in config.WORKSPACE_BASE_DIR.glob("*/state.json"):
        try:
            run = _normalize_run(json.loads(state_path.read_text(encoding="utf-8")))
            if run["run_id"] not in items_by_id:
                items_by_id[run["run_id"]] = run
        except Exception as exc:
            logger.warning(f"Failed to parse state file {state_path}: {exc}")

    runs = list(items_by_id.values())
    runs.sort(key=lambda item: _parse_iso(item.get("created_at")), reverse=True)
    return runs


def _workspace_path(run: Dict[str, Any]) -> Path:
    path = Path(run.get("log_path", "")).resolve()
    if path.exists():
        return path
    return (config.WORKSPACE_BASE_DIR / run["run_id"]).resolve()


def _read_plan_log(log_path: Path) -> str:
    if not log_path.exists():
        return "Plan created"
    try:
        return log_path.read_text(encoding="utf-8")
    except Exception:
        return "Plan created"


def _run_apply_pipeline(run: Dict[str, Any]) -> Dict[str, Any]:
    workspace_path = _workspace_path(run)
    log_path = workspace_manager.get_log_path(workspace_path)

    run["status"] = "applying"
    run["error"] = None
    _save_run(run)

    if shutil.which("terraform") is None:
        run["status"] = "failed"
        run["error"] = "Terraform CLI is not installed or not available in PATH."
        return _save_run(run)

    start = time.time()
    with TerraformRunner(workspace_path, log_path) as runner:
        success, plan_summary, outputs, error = runner.run_pipeline("apply")
    run["duration"] = int(time.time() - start)

    if success:
        run["status"] = "completed"
        run["plan_output"] = plan_summary or _read_plan_log(log_path)
        run["outputs"] = outputs
        run["error"] = None
    else:
        run["status"] = "failed"
        run["error"] = error or "Terraform apply failed"

    return _save_run(run)


def _run_destroy_pipeline(run: Dict[str, Any]) -> Dict[str, Any]:
    workspace_path = _workspace_path(run)
    log_path = workspace_manager.get_log_path(workspace_path)

    run["status"] = "destroying"
    run["error"] = None
    _save_run(run)

    if shutil.which("terraform") is None:
        run["status"] = "failed"
        run["error"] = "Terraform CLI is not installed or not available in PATH."
        return _save_run(run)

    with TerraformRunner(workspace_path, log_path) as runner:
        success, _, _, error = runner.run_pipeline("destroy")

    if success:
        run["status"] = "destroyed"
        run["error"] = None
    else:
        run["status"] = "failed"
        run["error"] = error or "Terraform destroy failed"

    return _save_run(run)


def _delete_all_run_workspaces() -> int:
    deleted = 0
    if not config.WORKSPACE_BASE_DIR.exists():
        return deleted
    for entry in config.WORKSPACE_BASE_DIR.iterdir():
        if not entry.is_dir():
            continue
        if not entry.name.startswith("run_"):
            continue
        try:
            shutil.rmtree(entry)
            deleted += 1
        except Exception as exc:
            logger.warning(f"Failed to delete workspace '{entry}': {exc}")
    return deleted


@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
    logger.info(f"Default Provider: {config.DEFAULT_PROVIDER.upper()}")
    logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")
    logger.info(f"MongoDB Connected: {db.is_connected}")


@app.on_event("shutdown")
async def shutdown_event():
    db.close()
    logger.info("Application shutdown completed")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/templates")
async def list_templates(provider: Optional[str] = Query(default=None), category: Optional[str] = Query(default=None)) -> List[Dict[str, Any]]:
    """Get templates, optionally filtered by provider and/or grouped by category."""
    if category:
        return get_templates_by_category(category=category, provider=provider)
    return get_template_catalog(provider=provider)


@app.get("/regions")
async def list_regions(provider: str = Query(default="aws")) -> List[Dict[str, str]]:
    """Get all available regions for a cloud provider."""
    provider = provider.lower()
    
    if provider == "aws":
        return [
            {"code": code, "name": name, "provider": "aws"}
            for code, name in AWS_REGIONS.items()
        ]
    elif provider == "gcp":
        return [
            {"code": code, "name": name, "provider": "gcp"}
            for code, name in GCP_REGIONS.items()
        ]
    else:
        raise HTTPException(status_code=400, detail=f"Invalid provider: {provider}. Must be 'aws' or 'gcp'.")


@app.get("/dashboard/overview")
async def dashboard_overview(days: int = Query(default=30, ge=7, le=120)) -> Dict[str, Any]:
    return build_dashboard_overview(_list_runs(), days=days)


@app.get("/resources")
async def resources_overview(
    provider: str = Query(default="all"),
    resource_type: str = Query(default="all", alias="type"),
    search: str = Query(default=""),
    sort: str = Query(default="updated_desc"),
    view: str = Query(default="list"),
) -> Dict[str, Any]:
    payload = build_resources_payload(
        _list_runs(),
        provider=provider,
        resource_type=resource_type,
        search=search,
        sort=sort,
    )
    payload["view"] = view
    return payload


@app.get("/analytics/summary")
async def analytics_summary(range: str = Query(default="30d")) -> Dict[str, Any]:
    return build_analytics_summary(_list_runs(), range_key=range)


@app.get("/monitoring/overview")
async def monitoring_overview() -> Dict[str, Any]:
    return build_monitoring_overview(_list_runs())


@app.get("/settings")
async def get_settings() -> Dict[str, Any]:
    return settings_store.get()


@app.put("/settings")
async def put_settings(payload: SettingsUpdateRequest) -> Dict[str, Any]:
    return settings_store.update(payload.settings)


@app.post("/admin/delete-all-runs")
async def delete_all_runs(payload: AdminConfirmRequest) -> Dict[str, Any]:
    if payload.confirmation != "DELETE ALL RUNS":
        raise HTTPException(status_code=400, detail="Invalid confirmation phrase")

    db_counts = db.delete_all_runs() if db.is_connected else {"runs_deleted": 0, "chat_messages_deleted": 0}
    files_deleted = _delete_all_run_workspaces()
    return {
        "ok": True,
        "runs_deleted_db": db_counts["runs_deleted"],
        "chat_messages_deleted_db": db_counts["chat_messages_deleted"],
        "workspaces_deleted": files_deleted,
    }


@app.post("/admin/reset-application")
async def reset_application(payload: AdminConfirmRequest) -> Dict[str, Any]:
    if payload.confirmation != "RESET APPLICATION":
        raise HTTPException(status_code=400, detail="Invalid confirmation phrase")

    db_counts = db.delete_all_runs() if db.is_connected else {"runs_deleted": 0, "chat_messages_deleted": 0}
    files_deleted = _delete_all_run_workspaces()
    settings = settings_store.reset()

    return {
        "ok": True,
        "runs_deleted_db": db_counts["runs_deleted"],
        "chat_messages_deleted_db": db_counts["chat_messages_deleted"],
        "workspaces_deleted": files_deleted,
        "settings_updated_at": settings.get("updated_at"),
    }


@app.get("/runs", response_model=List[RunResponse])
async def list_runs() -> List[Dict[str, Any]]:
    return _list_runs()


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str) -> Dict[str, Any]:
    return _load_run_or_404(run_id)


@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(request: AgentRequest) -> Dict[str, Any]:
    run_id, workspace_path = workspace_manager.create_run_workspace()
    workspace_path = workspace_path.resolve()
    log_path = workspace_manager.get_log_path(workspace_path)

    template_name = None
    effective_request = (request.request or "").strip()
    if request.method == "template":
        effective_request, template_name = compose_template_request(
            template_id=request.template_id or "",
            provider=request.provider,
            region=request.region,
            template_inputs=request.template_inputs or {},
        )

    run: Dict[str, Any] = {
        "run_id": run_id,
        "status": "created",
        "provider": request.provider,
        "log_path": str(workspace_path),
        "request": effective_request,
        "region": request.region,
        "method": request.method,
        "template_id": request.template_id,
        "template_name": template_name,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _save_run(run, is_new=True)

    run["status"] = "planning"
    _save_run(run)

    try:
        terraform_bundle, fallback_reason = _generate_bundle_with_fallback(effective_request, request.provider)
        used_mock = fallback_reason is not None
        is_valid, error_msg = SecurityChecker.validate(terraform_bundle, request.provider)
        if not is_valid:
            run["status"] = "failed"
            run["error"] = error_msg
            return _save_run(run)

        workspace_manager.write_terraform_files(workspace_path, terraform_bundle)
        request_snapshot = request.model_copy(update={"request": effective_request})
        workspace_manager.write_request_json(workspace_path, request_snapshot)

        if used_mock:
            run["status"] = "planned"
            run["error"] = None
            run["plan_output"] = (
                f"Mock plan generated for local testing. "
                f"Reason: {fallback_reason}. "
                f"Use Approve to simulate apply."
            )
            run["cost_estimate"] = {"mode": "mock", "reason": fallback_reason}
            run["estimated_cost"] = 0.0
            run["resources_add"] = 2
            run["resources_change"] = 0
            run["resources_destroy"] = 0
            return _save_run(run)

        if shutil.which("terraform") is None:
            run["status"] = "planned"
            run["plan_output"] = "Terraform CLI not found. Plan/apply steps are unavailable until Terraform is installed."
            return _save_run(run)

        with TerraformRunner(workspace_path, log_path) as runner:
            init_ok = runner._run_init()
            plan_summary = runner._run_plan() if init_ok else ""

        if not init_ok or not plan_summary:
            run["status"] = "failed"
            run["error"] = "Terraform plan failed"
        else:
            run["status"] = "planned"
            run["plan_output"] = _read_plan_log(log_path)
            run["error"] = None

        run = _save_run(run)

        if request.auto_approve and run["status"] == "planned":
            run["status"] = "approved"
            _save_run(run)
            run = _run_apply_pipeline(run)

        return run

    except Exception as exc:
        run["status"] = "failed"
        run["error"] = str(exc)
        return _save_run(run)


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str) -> Dict[str, Any]:
    run = _load_run_or_404(run_id)
    if run["status"] in {"completed", "destroyed", "destroying"}:
        return run

    if _is_mock_run(run):
        run["status"] = "completed"
        run["duration"] = 0
        run["outputs"] = {
            "mock_mode": True,
            "message": "Mock apply completed successfully for UI testing.",
            "run_id": run_id,
        }
        run["error"] = None
        return _save_run(run)

    run["status"] = "approved"
    _save_run(run)
    return _run_apply_pipeline(run)


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str) -> Dict[str, Any]:
    run = _load_run_or_404(run_id)
    run["status"] = "failed"
    run["error"] = "Run rejected by user"
    return _save_run(run)


@app.post("/runs/{run_id}/destroy", response_model=RunResponse)
async def destroy_run(run_id: str) -> Dict[str, Any]:
    run = _load_run_or_404(run_id)
    if run["status"] == "destroyed":
        return run
    if _is_mock_run(run):
        run["status"] = "destroyed"
        run["error"] = None
        return _save_run(run)
    return _run_destroy_pipeline(run)


@app.post("/runs/{run_id}/chat", response_model=ChatResponse)
async def chat_about_run(run_id: str, payload: ChatRequest) -> ChatResponse:
    """Chat about a Terraform run using LLM to analyze the infrastructure"""
    run = _load_run_or_404(run_id)
    timestamp = _now_iso()
    
    # Load Terraform files for context
    terraform_code = _load_terraform_files(run_id)
    
    # Build context for the LLM
    context_parts = [
        f"You are a helpful infrastructure expert analyzing a Terraform deployment.",
        f"",
        f"Run Details:",
        f"- Run ID: {run_id}",
        f"- Status: {run['status']}",
        f"- Provider: {run['provider'].upper()}",
        f"- Region: {run.get('region', 'N/A')}",
        f"- Request: {run.get('request', 'N/A')}",
    ]
    
    # Add Terraform code to context
    if terraform_code:
        context_parts.append("\nTerraform Configuration:")
        if terraform_code.get("main_tf"):
            context_parts.append("\nmain.tf:")
            context_parts.append("```hcl")
            context_parts.append(terraform_code["main_tf"])
            context_parts.append("```")
        if terraform_code.get("variables_tf"):
            context_parts.append("\nvariables.tf:")
            context_parts.append("```hcl")
            context_parts.append(terraform_code["variables_tf"])
            context_parts.append("```")
    
    # Add plan output if available
    if run.get("plan_output"):
        context_parts.append("\nTerraform Plan Output:")
        context_parts.append("```")
        context_parts.append(run["plan_output"][:1000])  # Limit to avoid token overflow
        context_parts.append("```")
    
    context_parts.append(f"\nUser Question: {payload.message}")
    context_parts.append("\nProvide a helpful, concise answer based on the Terraform configuration above.")
    
    context = "\n".join(context_parts)
    
    # Use LLM to generate response
    try:
        response_text = await llm_generator.generate_chat_response(context, payload.message)
    except Exception as e:
        logger.warning(f"LLM chat failed: {e}, falling back to basic response")
        # Fallback to basic response
        response_parts = [f"Run {run_id} is currently in '{run['status']}' state."]
        if run.get("plan_output"):
            response_parts.append("Plan output is available in the Plan tab.")
        if run.get("error"):
            response_parts.append(f"Latest error: {run['error']}")
        response_text = " ".join(response_parts)
    
    # Save chat history
    if db.is_connected:
        db.save_chat_message(run_id, "user", payload.message)
        db.save_chat_message(run_id, "assistant", response_text)

    return ChatResponse(response=response_text, timestamp=timestamp)


@app.post("/runs/{run_id}/edit", response_model=RunResponse)
async def edit_run(run_id: str, payload: ChatRequest) -> Dict[str, Any]:
    run = _load_run_or_404(run_id)
    workspace_path = _workspace_path(run)

    run["status"] = "planning"
    run["error"] = None
    _save_run(run)

    try:
        current_files = workspace_manager.read_terraform_files(workspace_path)
        if not current_files:
            raise ValueError("No Terraform files found for this run.")

        refined_bundle, fallback_reason = _refine_bundle_with_fallback(
            base_request=run.get("request") or "",
            current_code={
                "main_tf": current_files.get("main.tf", ""),
                "variables_tf": current_files.get("variables.tf", ""),
                "outputs_tf": current_files.get("outputs.tf", ""),
            },
            feedback=payload.message,
            provider=run["provider"],
        )
        used_mock = fallback_reason is not None

        workspace_manager.write_terraform_files(workspace_path, refined_bundle)

        if used_mock:
            run["status"] = "planned"
            run["error"] = None
            run["plan_output"] = f"Mock re-plan generated for local testing. Reason: {fallback_reason}."
            run["cost_estimate"] = {"mode": "mock", "reason": fallback_reason}
            run["estimated_cost"] = 0.0
            run["resources_add"] = 2
            run["resources_change"] = 1
            run["resources_destroy"] = 0
            return _save_run(run)

        if shutil.which("terraform") is None:
            run["status"] = "planned"
            run["plan_output"] = "Terraform CLI not found. Replan completed for code only."
            return _save_run(run)

        log_path = workspace_manager.get_log_path(workspace_path)
        with TerraformRunner(workspace_path, log_path) as runner:
            init_ok = runner._run_init()
            plan_summary = runner._run_plan() if init_ok else ""

        if not init_ok or not plan_summary:
            run["status"] = "failed"
            run["error"] = "Terraform re-plan failed"
        else:
            run["status"] = "planned"
            run["plan_output"] = _read_plan_log(log_path)
            run["error"] = None

        return _save_run(run)

    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"Edit failed: {exc}"
        return _save_run(run)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)
