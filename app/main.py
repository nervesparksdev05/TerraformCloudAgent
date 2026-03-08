"""app/main.py — TerraBot FastAPI entry point (AWS-only, interactive workflow)."""
from __future__ import annotations

import asyncio
import os
import redis.asyncio as redis
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.core.auth import get_current_user
from app.rate_limiter import check_rate_limit
from app.models.schemas import (
    AgentRequest, RunResponse, RunStatus,
    ChatRequest, ChatResponse,
)
from app.models.conversation_schemas import (
    ConversationCreateResponse, ChatMessage, ChatMessageResponse, FeedbackRequest,
)
from app.services.run_manager import RunManager
from app.services.workflow_engine import WorkflowEngine
from app.services.llm_generator import LLMGenerator
from app.services.conversation_manager import ConversationManager
from app.services.email_service import email_service
from app.services.user_service import user_service

setup_logging(log_dir=str(config.LOGS_DIR), log_level="DEBUG" if config.DEBUG else "INFO")
logger = get_logger(__name__)

# ── Service singletons ────────────────────────────────────────────────────────
run_manager          = RunManager(base_dir=str(config.WORKSPACE_BASE_DIR))
workflow_engine      = WorkflowEngine()
llm_generator        = LLMGenerator()
conversation_manager = ConversationManager()

redis_client: Optional[redis.Redis] = None

logger.info("Starting %s v%s (AWS Free Tier mode)", config.APP_NAME, config.APP_VERSION)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client

    # ── Redis ─────────────────────────────────────────────────────────────
    try:
        redis_url = getattr(config, "REDIS_URL", None) or os.getenv("REDIS_URL")
        if redis_url:
            redis_client = redis.from_url(redis_url, decode_responses=True)
            await redis_client.ping()
            logger.info("Redis connected: %s", redis_url)
        else:
            logger.warning("REDIS_URL not set — rate limiting disabled.")
    except Exception as e:
        logger.warning("Redis connection failed (%s) — rate limiting disabled.", e)
        redis_client = None

    # ── MCP Servers ───────────────────────────────────────────────────────
    from app.services.mcp_service import mcp_manager
    mcp_servers = {}
    if config.ENABLE_AWS_MCP:
        mcp_servers["aws"] = config.AWS_MCP_SERVER
    if config.ENABLE_TERRAFORM_MCP:
        mcp_servers["terraform"] = config.TERRAFORM_MCP_SERVER

    if mcp_servers:
        try:
            await mcp_manager.initialize_all(mcp_servers)
            logger.info("MCP servers initialized: %s", list(mcp_servers.keys()))
        except Exception as e:
            # Non-fatal — app still works without MCP
            logger.error("MCP server initialization failed: %s — continuing without MCP.", e)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed.")

    # FIX: Only close MCP here — removed duplicate @app.on_event("shutdown")
    try:
        await mcp_manager.close_all()
        logger.info("MCP sessions closed.")
    except Exception as e:
        logger.warning("Error closing MCP sessions: %s", e)

    logger.info("Application shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " — AWS Interactive Workflow",
    version=config.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:5174",
        "http://localhost:3000", "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_identity(
    user: Optional[Dict], 
    x_user_id: Optional[str], 
    session_id: Optional[str] = None
) -> tuple[Optional[str], Optional[str]]:
    """
    Robust identity extraction with fallbacks:
    1. Authenticated user (Firebase/Auth)
    2. X-User-ID Header (Dev/Local fallback)
    3. Session ID (to group anonymous traces)
    4. "anonymous" (final fallback)
    """
    # 1. Firebase Auth
    if user:
        uid = user.get("uid") or user.get("user_id")
        email = user.get("email") or user.get("name")
        if uid:
            return uid, email
    
    # 2. Header Fallback
    if x_user_id:
        return x_user_id, f"{x_user_id}@header"

    # 3. Session Fallback
    if session_id:
        # Use session_id as the user_id if we have nothing else
        return session_id, f"anon-{session_id[:8]}"

    return "anonymous", "anonymous"


def _get_rate_id(user: Optional[Dict], x_user_id: Optional[str]) -> str:
    uid, _ = _extract_identity(user, x_user_id)
    return uid or "anonymous"


def _build_agent_request(terraform_params: dict) -> AgentRequest:
    provider_choice = str(terraform_params.get("cloud_provider", "aws")).lower()
    return AgentRequest(
        request=terraform_params,
        provider=provider_choice,
        auto_approve=False,
    )


async def _launch_planning(session_id: str, background_tasks: Optional[BackgroundTasks] = None) -> str:
    """Build AgentRequest from a completed session, create a run, and start planning."""
    from app.services import langfuse_service
    
    terraform_params = conversation_manager.build_terraform_request(session_id)
    agent_request    = _build_agent_request(terraform_params)
    
    # Persist user identity in AgentRequest for background task retrieval
    session = conversation_manager.get_session(session_id)
    if session:
        # Robust fallback: if session has no user_id (anonymous session), use session_id itself
        _user_id = session.user_id or session_id
        _username = session.username or f"anon-{session_id[:8]}"
        
        agent_request.user_id = _user_id
        agent_request.username = _username
        logger.info("[%s] Persisted user identity in AgentRequest: user_id=%s", session_id, _user_id)

    run              = run_manager.create_run(agent_request)
    run.metadata     = {
        "conversation_params": conversation_manager.get_collected_parameters(session_id),
        "session_id": session_id,
    }
    run_manager.save_run_state(run.run_id, run)
    conversation_manager.add_run_to_session(session_id, run.run_id)

    if background_tasks:
        background_tasks.add_task(workflow_engine.execute_planning_phase, run.run_id, agent_request)
    else:
        asyncio.create_task(workflow_engine.execute_planning_phase(run.run_id, agent_request))

    logger.info("[%s] Planning started → run_id=%s", session_id, run.run_id)
    return run.run_id


# ── Root & health ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "app":     config.APP_NAME,
        "version": config.APP_VERSION,
        "provider": "AWS",
        "conversation_workflow": {
            "1_start":   "POST /conversations?owner=<>&repo=<>",
            "2_chat":    "POST /conversations/{id}/message  (repeat until is_complete=true)",
            "3_monitor": "GET  /runs/{run_id}",
            "4_review":  "GET  /runs/{run_id}/files  or  POST /runs/{run_id}/chat",
            "5_deploy":  "POST /runs/{run_id}/approve",
            "6_destroy": "POST /runs/{run_id}/destroy",
        },
        "docs": "/docs",
    }


@app.get("/health")
async def health_check():
    return {
        "status":        "healthy",
        "version":       config.APP_VERSION,
        "provider":      "aws",
        "auth_required": config.REQUIRE_AUTH,
        "redis":         redis_client is not None,
        "mcp_terraform": config.ENABLE_TERRAFORM_MCP,
        "mcp_aws":       config.ENABLE_AWS_MCP,
    }


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.post("/auth/sync-user")
async def sync_user(user: Optional[Dict] = Depends(get_current_user)):
    if not user:
        return {"status": "skipped", "message": "Auth disabled"}
    try:
        doc = user_service.upsert_user(user)
        return {"status": "ok", "user": doc}
    except Exception as e:
        logger.error("sync_user failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/auth/verify")
async def verify_auth(user: Optional[Dict] = Depends(get_current_user)):
    if not config.REQUIRE_AUTH:
        return {"authenticated": False, "message": "Authentication disabled"}
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return {
        "authenticated": True,
        "user": {"uid": user.get("uid"), "email": user.get("email"), "name": user.get("name")},
    }


# ── Conversation endpoints ────────────────────────────────────────────────────

@app.post("/conversations", response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(
    owner: str = "",
    repo: str = "",
    github_token: str = "",
    github_branch: str = "",
    user: Optional[Dict] = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    if not owner.strip() or not repo.strip():
        raise HTTPException(status_code=400, detail="owner and repo are required.")

    if redis_client:
        await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)

    try:
        from app.services import langfuse_service
        
        # Extract identity with robust fallbacks
        user_id, username = _extract_identity(user, x_user_id)
        
        with langfuse_service.user_context(user_id=user_id, username=username):
            result = await conversation_manager.create_session(
                owner=owner, repo=repo,
                github_token=github_token, github_branch=github_branch,
                user_id=user_id, username=username,
            )
        return ConversationCreateResponse(
            session_id=result["session_id"],
            bot_response=result["bot_response"],
            suggestions=result.get("suggestions", []),
        )
    except Exception as e:
        logger.error("create_conversation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/message", response_model=ChatMessageResponse)
async def send_message(
    session_id: str,
    chat_message: ChatMessage,
    background_tasks: BackgroundTasks,
    user: Optional[Dict] = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    if redis_client:
        await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)

    try:
        from app.services import langfuse_service
        
        with langfuse_service.user_context(user_id=session.user_id, username=session.username, session_id=session_id):
            response = await conversation_manager.process_message(
                session_id=session_id,
                user_message=chat_message.message,
            )
        if response.is_complete:
            # Guard: only auto-generate if no run already exists for this session
            existing_params = conversation_manager.get_collected_parameters(session_id)
            existing_runs = existing_params.get("run_ids", [])
            if not existing_runs:
                try:
                    response.run_id = await _launch_planning(session_id, background_tasks)
                except Exception as e:
                    logger.error("[%s] Auto-generate failed: %s", session_id, e, exc_info=True)

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] send_message failed: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/message/stream")
async def stream_message(
    session_id: str,
    chat_message: ChatMessage,
    user: Optional[Dict] = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    import json

    async def generate():
        if redis_client:
            await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)

        session = conversation_manager.get_session(session_id)
        if not session:
            yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
            return

        try:
            from app.services import langfuse_service
            
            with langfuse_service.user_context(user_id=session.user_id, username=session.username, session_id=session_id):
                response = await conversation_manager.process_message(
                    session_id=session_id,
                    user_message=chat_message.message,
                )
        except Exception as e:
            logger.error("[%s] stream process_message failed: %s", session_id, e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        text = response.bot_response or ""
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            yield f"data: {json.dumps({'content': text[i:i + chunk_size]})}\n\n"
            await asyncio.sleep(0.01)

        run_id = None
        if response.is_complete:
            # Guard: only auto-generate if no run already exists for this session
            existing_params = conversation_manager.get_collected_parameters(session_id)
            existing_runs = existing_params.get("run_ids", [])
            if not existing_runs:
                try:
                    run_id = await _launch_planning(session_id)
                except Exception as e:
                    logger.error("[%s] stream auto-generate failed: %s", session_id, e, exc_info=True)

        completion = {
            "done":         True,
            "is_complete":  response.is_complete,
            "suggestions":  response.suggestions or [],
            "collected_parameters": response.collected_parameters,
        }
        if run_id:
            completion["run_id"] = run_id

        yield f"data: {json.dumps(completion)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/conversations/{session_id}/feedback", status_code=202)
async def submit_feedback(
    session_id: str,
    feedback: FeedbackRequest,
    user: Optional[Dict] = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    if redis_client:
        await check_rate_limit(_rate_id(user, x_user_id), redis_client)

    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        from app.services import langfuse_service

        # Prefer trace_id from request (targets specific message),
        # fallback to session's last_trace_id
        trace_id = feedback.trace_id or session.last_trace_id
        if trace_id:
            # Score the actual conversation turn trace
            langfuse_service.log_score(
                trace_id=trace_id,
                name="user-feedback",
                value=float(feedback.rating),
                comment=feedback.comment
            )
        else:
            # Fallback: create an ad-hoc trace for feedback if no prior trace exists
            trace = langfuse_service.create_trace(
                name="user-feedback-submission",
                session_id=session_id,
                user_id=session.user_id,
                username=session.username,
                input={"rating": feedback.rating, "comment": feedback.comment}
            )
            if trace:
                langfuse_service.log_score(
                    trace_id=trace.id,
                    name="user-feedback",
                    value=float(feedback.rating),
                    comment=feedback.comment
                )
        return {"message": "Feedback submitted successfully"}
    except Exception as e:
        logger.error("[%s] submit_feedback failed: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    user: Optional[Dict] = Depends(get_current_user),
):
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session.dict()


@app.get("/conversations")
async def list_conversations(
    limit: int = 20,
    user: Dict = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    if redis_client:
        await check_rate_limit(_rate_id(user, x_user_id), redis_client)
    return conversation_manager.list_sessions(limit=limit)


@app.get("/sessions")
async def list_sessions(limit: int = 20, user: Optional[Dict] = Depends(get_current_user)):
    try:
        return conversation_manager.list_sessions(limit=limit)
    except Exception as e:
        logger.error("list_sessions failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: Dict = Depends(get_current_user)):
    try:
        if conversation_manager.delete_session(session_id):
            return {"message": "Session deleted successfully"}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_session %s failed: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/generate", response_model=RunResponse, status_code=202)
async def generate_terraform_from_conversation(
    session_id: str,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user),
):
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if not session.is_complete:
        raise HTTPException(status_code=400, detail="Conversation not complete yet.")

    try:
        run_id = await _launch_planning(session_id, background_tasks)
        return run_manager.get_run(run_id)
    except Exception as e:
        logger.error("[%s] generate failed: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Run endpoints ─────────────────────────────────────────────────────────────

@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(
    request: AgentRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    if redis_client:
        await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)
    request.provider = "aws"
    try:
        from app.services import langfuse_service
        
        # Extract identity with robust fallbacks
        user_id, username = _extract_identity(user, x_user_id)
        
        # Explicitly assign to request so it is persisted to disk/metadata
        request.user_id = user_id
        request.username = username

        with langfuse_service.user_context(user_id=user_id, username=username):
            run = run_manager.create_run(request)
            logger.info("[%s] Created AWS run", run.run_id)
            background_tasks.add_task(workflow_engine.execute_planning_phase, run.run_id, request)
            return run
    except Exception as e:
        logger.error("create_run failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.post("/runs/{run_id}/chat", response_model=ChatResponse)
async def chat_about_run(
    run_id: str,
    chat_request: ChatRequest,
    user: Dict = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Chat not available in status: {run.status}")

    if run.status == RunStatus.PLANNED:
        run_manager.update_run_status(run_id, RunStatus.REVIEWING)

    if redis_client:
        await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)

    try:
        from app.services import langfuse_service
        
        # Extract identity with robust fallbacks
        user_id, username = _extract_identity(user, x_user_id)
        _session_id = (run.metadata or {}).get("session_id")
        
        with langfuse_service.user_context(user_id=user_id, username=username, session_id=_session_id):
            context = (
                f"Explain the Terraform plan briefly using AWS terminology.\n\n"
                f"PLAN:\n{run.plan_output or 'Not available'}\n\n"
                f"QUESTION: {chat_request.message}"
            )
            text = await llm_generator.chat_about_plan(
                context,
                session_id=_session_id,
                user_id=_user_id,
                username=_username,
            )
            return ChatResponse(response=text, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error("[%s] chat_about_run failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/edit", response_model=RunResponse)
async def edit_run(
    run_id: str,
    edit_request: ChatRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(get_current_user),
    x_user_id: Optional[str] = Header(None),
):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit run in status: {run.status}")

    if redis_client:
        await check_rate_limit(_get_rate_id(user, x_user_id), redis_client)
    
    try:
        from app.services import langfuse_service
        
        # Extract identity with robust fallbacks
        _session_id = (run.metadata or {}).get("session_id")
        user_id, username = _extract_identity(user, x_user_id, session_id=_session_id)
        
        with langfuse_service.user_context(user_id=user_id, username=username, session_id=_session_id):
            # Create a mock AgentRequest to hold identity for the background task
            # (edit_run often passes request=None to execute_planning_phase)
            temp_request = AgentRequest(request=edit_request.message, user_id=user_id, username=username)
            
            run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
            background_tasks.add_task(
                workflow_engine.execute_planning_phase,
                run_id=run.run_id, request=temp_request, feedback=edit_request.message,
            )
            return run
    except Exception as e:
        logger.error("[%s] edit_run failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}/files")
async def get_run_files(run_id: str, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    try:
        workspace = run_manager.get_workspace_path(run_id)
        files = {}
        for fname, key in [("main.tf", "main_tf"), ("variables.tf", "variables_tf"), ("outputs.tf", "outputs_tf")]:
            p = workspace / fname
            if p.exists():
                files[key] = p.read_text(encoding="utf-8")
        return {"run_id": run_id, "files": files, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error("[%s] get_run_files failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/files", response_model=RunResponse)
async def edit_run_files(run_id: str, files: dict, background_tasks: BackgroundTasks, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit files in status: {run.status}")
    if "main_tf" not in files:
        raise HTTPException(status_code=400, detail="main_tf is required.")

    workspace = run_manager.get_workspace_path(run_id)
    for key, fname in [("main_tf", "main.tf"), ("variables_tf", "variables.tf"), ("outputs_tf", "outputs.tf")]:
        if key in files:
            (workspace / fname).write_text(files[key], encoding="utf-8")

    try:
        from app.services import langfuse_service
        _user_id = user.get("uid") if user else None
        _username = user.get("email") if user else None
        
        with langfuse_service.user_context(user_id=_user_id, username=_username):
            run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
            # revalidate_and_replan now re-sanitizes before planning
            background_tasks.add_task(workflow_engine.revalidate_and_replan, run_id, "aws")
            return run
    except Exception as e:
        logger.error("[%s] edit_run_files failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str, background_tasks: BackgroundTasks, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot approve run in status: {run.status}")

    try:
        from app.services import langfuse_service
        _user_id = user.get("uid") if user else None
        _username = user.get("email") if user else None
        
        with langfuse_service.user_context(user_id=_user_id, username=_username):
            run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
            logger.info("[%s] Run approved", run_id)
            background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
            return run
    except Exception as e:
        logger.error("[%s] approve_run failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.REJECTED]:
        raise HTTPException(status_code=400, detail=f"Cannot reject run in status: {run.status}")

    run = run_manager.update_run_status(run_id, RunStatus.REJECTED, error="Rejected by user")
    logger.info("[%s] Run rejected", run_id)
    return run


@app.post("/runs/{run_id}/destroy", response_model=RunResponse)
async def destroy_run(run_id: str, background_tasks: BackgroundTasks, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Can only destroy COMPLETED runs.")

    try:
        from app.services import langfuse_service
        _user_id = user.get("uid") if user else None
        _username = user.get("email") if user else None
        
        with langfuse_service.user_context(user_id=_user_id, username=_username):
            background_tasks.add_task(workflow_engine.execute_destroy_phase, run_id)
            return run_manager.update_run_status(run_id, RunStatus.DESTROYING)
    except Exception as e:
        logger.error("[%s] destroy_run failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/runs/{run_id}/redeploy", response_model=RunResponse)
async def redeploy_run(run_id: str, background_tasks: BackgroundTasks, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.DESTROYED, RunStatus.REJECTED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot redeploy run in status: {run.status}. Use 'Approve' if the run is still in review."
        )

    try:
        from app.services import langfuse_service
        _user_id = user.get("uid") if user else None
        _username = user.get("email") if user else None
        
        with langfuse_service.user_context(user_id=_user_id, username=_username):
            run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
            logger.info("[%s] Redeploy triggered", run_id)
            background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
            return run
    except Exception as e:
        logger.error("[%s] redeploy_run failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Email approval workflow ───────────────────────────────────────────────────

@app.post("/runs/{run_id}/send-for-approval")
async def send_approval_email(run_id: str, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        files = run_manager.get_run_files(run_id)
        if not files or "main_tf" not in files:
            raise HTTPException(status_code=400, detail="Terraform files not found or incomplete")

        user_email = user.get("email")
        if not user_email:
            raise HTTPException(status_code=400, detail="User email not found in token")

        summary = {"resources": (run.metadata or {}).get("plan_summary", [])}
        success = email_service.send_terraform_approval_email(
            to_email=user_email, run_id=run_id,
            terraform_files=files, terraform_summary=summary,
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP configuration.")

        if not run.approval_info:
            run.approval_info = {}
        run.approval_info.update({
            "email_sent_at": datetime.utcnow().isoformat(),
            "email_sent_to": user_email,
            "status": "pending_email_approval",
        })
        run_manager.save_run_state(run_id, run)
        return {"message": "Approval email sent successfully", "email": user_email}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("send_approval_email %s: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/approve/{token}")
async def approve_via_email(token: str, background_tasks: BackgroundTasks):
    from fastapi.responses import HTMLResponse

    data = email_service.verify_approval_token(token)
    if not data:
        return HTMLResponse("<h1> Invalid or expired token</h1>", status_code=400)
    if data.get("action") != "approve":
        return HTMLResponse("<h1> Invalid token — this is not an approval token</h1>", status_code=400)

    run_id     = data.get("run_id")
    user_email = data.get("user_email")
    run        = run_manager.get_run(run_id)
    if not run:
        return HTMLResponse("<h1> Run not found</h1>", status_code=404)
    if run.status == RunStatus.APPROVED:
        return HTMLResponse(f"<h1> Already Approved</h1><p>Run {run_id} was already approved.</p>")
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        return HTMLResponse(f"<h1> Cannot Approve</h1><p>Status is {run.status}.</p>", status_code=400)

    from app.services import langfuse_service
    with langfuse_service.user_context(username=user_email):
        run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
        if not run.approval_info:
            run.approval_info = {}
        run.approval_info.update({
            "approved_at": datetime.utcnow().isoformat(),
            "approved_by": user_email, "method": "email_link", "status": "approved",
        })
        run_manager.save_run_state(run_id, run)
        background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
        email_service.send_approval_confirmation_email(user_email, run_id, approved=True)

    return HTMLResponse(f"""
    <html><head><title>Approved</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:50px">
      <h1 style="color:#10b981"> Run Approved & Apply Triggered</h1>
      <p>Run ID: <code>{run_id}</code></p>
      <p>Terraform Apply has started. You can close this window.</p>
    </body></html>
    """)


@app.get("/reject/{token}")
async def reject_via_email(token: str, reason: str = "Rejected via email"):
    from fastapi.responses import HTMLResponse

    data = email_service.verify_approval_token(token)
    if not data:
        return HTMLResponse("<h1> Invalid or expired token</h1>", status_code=400)
    if data.get("action") != "reject":
        return HTMLResponse("<h1> Invalid token — this is not a rejection token</h1>", status_code=400)

    run_id     = data.get("run_id")
    user_email = data.get("user_email")
    run        = run_manager.get_run(run_id)
    if not run:
        return HTMLResponse("<h1> Run not found</h1>", status_code=404)
    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.REJECTED]:
        return HTMLResponse(f"<h1> Already in status {run.status}</h1>", status_code=400)

    updated_run = run_manager.update_run_status(run_id, RunStatus.REJECTED, error=f"Rejected by user: {reason}")
    if updated_run:
        if not updated_run.approval_info:
            updated_run.approval_info = {}
        updated_run.approval_info.update({
            "rejected_at": datetime.utcnow().isoformat(),
            "rejected_by": user_email, "rejection_reason": reason,
            "method": "email_link", "status": "rejected",
        })
        run_manager.save_run_state(run_id, updated_run)
    email_service.send_approval_confirmation_email(user_email, run_id, approved=False, reason=reason)

    return HTMLResponse(f"""
    <html><head><title>Rejected</title></head>
    <body style="font-family:sans-serif;text-align:center;padding:50px">
      <h1 style="color:#ef4444"> Run Rejected</h1>
      <p>Run ID: <code>{run_id}</code></p>
      <p>The configuration will not be applied.</p>
    </body></html>
    """)


@app.get("/runs/{run_id}/approval-status")
async def get_approval_status(run_id: str, user: Dict = Depends(get_current_user)):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"status": run.status, "approval_info": run.approval_info}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.HOST, port=config.PORT, reload=config.DEBUG)