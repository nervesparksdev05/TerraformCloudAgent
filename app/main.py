# app/main.py  ✅ UPDATED (provider chosen inside chat; removed from /conversations)

"""
FastAPI application - Main entry point (Unified)
Supports both direct execution and interactive workflow modes
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.models.schemas import (
    AgentRequest, RunResponse, RunStatus,
    ChatRequest, ChatResponse
)
from app.models.conversation_schemas import (
    ConversationCreateResponse,
    ChatMessage,
    ChatMessageResponse,
)
from app.services.run_manager import RunManager
from app.services.workflow_engine import WorkflowEngine
from app.services.llm_generator import LLMGenerator
from app.services.conversation_manager import ConversationManager

# Setup logging
setup_logging(
    log_dir=config.LOGS_DIR,
    log_level="DEBUG" if config.DEBUG else "INFO"
)
logger = get_logger(__name__)

# Initialize services (before app creation)
run_manager = RunManager(base_dir=config.WORKSPACE_BASE_DIR)
workflow_engine = WorkflowEngine()
llm_generator = LLMGenerator()
conversation_manager = ConversationManager()

logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
logger.info("Mode: Interactive Workflow")
logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")


def _normalize_provider(p: str) -> str:
    p = (p or "aws").strip().lower()
    aliases = {
        "aws": "aws",
        "amazon": "aws",
        "gcp": "gcp",
        "google": "gcp",
        "azure": "azure",
        "do": "digitalocean",
        "digitalocean": "digitalocean",
        "digital-ocean": "digitalocean",
    }
    return aliases.get(p, p)


SUPPORTED_PROVIDERS = ["aws", "gcp", "azure", "digitalocean"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started - Interactive Workflow Mode")
    logger.info(
        f"Supported providers: {', '.join([p.upper() if p!='digitalocean' else 'DigitalOcean' for p in SUPPORTED_PROVIDERS])}"
    )
    logger.info("Human-in-the-loop deployment with review, chat, and approval")
    yield
    logger.info("Application shutting down")


app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " - Interactive Workflow",
    version=config.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan,
)

# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@app.post("/conversations", response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(
    owner: str = "",
    repo: str = "",
    github_token: str = "",
    github_branch: str = "",
):
    """
    Start a README-driven conversational session.
    README is fetched via GitHub API using owner+repo only.
    Provider is chosen inside the chat (NOT here).
    """
    logger.info("Received create_conversation request: owner=%s, repo=%s", owner, repo)
    try:
        if not owner.strip() or not repo.strip():
            raise HTTPException(status_code=400, detail="owner and repo are required.")

        result = await conversation_manager.create_session(
            owner=owner,
            repo=repo,
            github_token=github_token,
            github_branch=github_branch,
        )
        return ConversationCreateResponse(
            session_id=result["session_id"],
            bot_response=result["bot_response"],
            suggestions=result.get("suggestions", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create conversation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/message", response_model=ChatMessageResponse)
async def send_message(session_id: str, chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """
    Send a message in an active conversation.
    Auto-generates Terraform run when conversation completes.
    """
    logger.info("[%s] Received message request", session_id)
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")

        response = await conversation_manager.process_message(
            session_id=session_id,
            user_message=chat_message.message
        )

        # Auto-generate Terraform when conversation completes
        if response.is_complete:
            try:
                terraform_params = conversation_manager.build_terraform_request(session_id)

                provider_norm = _normalize_provider(
                    str(terraform_params.get("cloud_provider") or session.provider or "aws")
                )
                if provider_norm not in SUPPORTED_PROVIDERS:
                    raise ValueError(
                        f"Provider not chosen yet. Expected one of {SUPPORTED_PROVIDERS}, got '{provider_norm}'."
                    )

                agent_request = AgentRequest(
                    request=terraform_params,
                    provider=provider_norm,     # ✅ derived from chat choice
                    auto_approve=False,
                )

                run = run_manager.create_run(agent_request)
                run.metadata = {
                    "conversation_params": conversation_manager.get_collected_parameters(session_id),
                    "session_id": session_id,
                }
                run_manager.save_run_state(run.run_id, run)

                background_tasks.add_task(
                    workflow_engine.execute_planning_phase,
                    run.run_id,
                    agent_request
                )

                response.run_id = run.run_id
                logger.info("[%s] Terraform generation started: run_id=%s", session_id, run.run_id)

            except Exception as e:
                logger.error("[%s] Failed to auto-generate Terraform: %s", session_id, e, exc_info=True)

        logger.debug("[%s] Message processed (complete: %s)", session_id, response.is_complete)
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Failed to process message: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    logger.debug("[%s] Fetching conversation details", session_id)
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")
    return session.dict()


@app.get("/sessions")
async def list_sessions(limit: int = 20):
    try:
        logger.info("Listing sessions (limit=%d)", limit)
        return conversation_manager.list_sessions(limit=limit)
    except Exception as e:
        logger.error("Failed to list sessions: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    try:
        logger.info("[%s] Deleting session", session_id)
        success = conversation_manager.delete_session(session_id)
        if success:
            return {"message": "Session deleted successfully"}
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete session %s: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/generate", response_model=RunResponse, status_code=202)
async def generate_terraform_from_conversation(session_id: str, background_tasks: BackgroundTasks):
    """
    Generate Terraform configuration from a completed conversation.
    """
    logger.info("[%s] Manual Terraform generation requested", session_id)
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")

        if not session.is_complete:
            raise HTTPException(
                status_code=400,
                detail="Conversation is not complete yet. Continue until the bot confirms completion."
            )

        terraform_params = conversation_manager.build_terraform_request(session_id)
        provider_norm = _normalize_provider(str(terraform_params.get("cloud_provider") or session.provider or "aws"))
        if provider_norm not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Provider not chosen. Pick one of: {SUPPORTED_PROVIDERS}")

        agent_request = AgentRequest(
            request=terraform_params,
            provider=provider_norm,
            auto_approve=False,
        )

        run = run_manager.create_run(agent_request)
        run.metadata = {
            "conversation_params": conversation_manager.get_collected_parameters(session_id),
            "session_id": session_id,
        }
        run_manager.save_run_state(run.run_id, run)

        try:
            conversation_manager.add_run_to_session(session_id, run.run_id)
        except Exception:
            pass

        logger.info("[%s] Creating run %s from conversation (provider=%s)", session_id, run.run_id, provider_norm)

        background_tasks.add_task(
            workflow_engine.execute_planning_phase,
            run.run_id,
            agent_request
        )

        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Failed to generate Terraform: %s", session_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STANDARD RUN ENDPOINTS (unchanged)
# ============================================================================

@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(request: AgentRequest, background_tasks: BackgroundTasks):
    try:
        request.provider = _normalize_provider(request.provider)
        if request.provider not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unsupported provider '{request.provider}'. Use one of: {SUPPORTED_PROVIDERS}")

        run = run_manager.create_run(request)
        logger.info("[%s] Created new %s run", run.run_id, request.provider.upper())
        background_tasks.add_task(workflow_engine.execute_planning_phase, run.run_id, request)
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create run: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.post("/runs/{run_id}/chat", response_model=ChatResponse)
async def chat_about_run(run_id: str, chat_request: ChatRequest):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Chat not available in status: {run.status}. Must be PLANNED or REVIEWING.")

    if run.status == RunStatus.PLANNED:
        run_manager.update_run_status(run_id, RunStatus.REVIEWING)

    try:
        context = (
            "Explain the Terraform plan briefly and clearly.\n\n"
            f"PROVIDER: {str(run.provider).upper()}\n\n"
            f"PLAN:\n{run.plan_output or 'Plan not available'}\n\n"
            f"QUESTION: {chat_request.message}"
        )
        response_text = await _chat_with_llm(context, provider=str(run.provider))
        return ChatResponse(response=response_text, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error("[%s] Chat failed: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/runs/{run_id}/edit", response_model=RunResponse)
async def edit_run(run_id: str, edit_request: ChatRequest, background_tasks: BackgroundTasks):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit run in status: {run.status}. Must be PLANNED or REVIEWING.")

    run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
    logger.info("[%s] Run edit requested: %s", run_id, edit_request.message)

    background_tasks.add_task(
        workflow_engine.execute_planning_phase,
        run_id=run.run_id,
        request=None,
        feedback=edit_request.message
    )
    return run


@app.get("/runs/{run_id}/files")
async def get_run_files(run_id: str):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    try:
        workspace_path = run_manager.get_workspace_path(run_id)
        files = {}

        for fname, key in [("main.tf", "main_tf"), ("variables.tf", "variables_tf"), ("outputs.tf", "outputs_tf")]:
            p = workspace_path / fname
            if p.exists():
                files[key] = p.read_text(encoding="utf-8")

        if not files:
            raise HTTPException(status_code=500, detail="Terraform files not found in workspace")

        logger.info("[%s] Files retrieved for review", run_id)
        return {"run_id": run_id, "files": files, "timestamp": datetime.now().isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Failed to read files: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to read files: {str(e)}")


@app.post("/runs/{run_id}/files", response_model=RunResponse)
async def edit_run_files(run_id: str, files: dict, background_tasks: BackgroundTasks):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit files in status: {run.status}. Must be PLANNED or REVIEWING.")

    if "main_tf" not in files:
        raise HTTPException(status_code=400, detail="main_tf is required.")

    try:
        workspace_path = run_manager.get_workspace_path(run_id)

        for file_key, filename in [("main_tf", "main.tf"), ("variables_tf", "variables.tf"), ("outputs_tf", "outputs.tf")]:
            if file_key in files:
                (workspace_path / filename).write_text(files[file_key], encoding="utf-8")
                logger.debug("[%s] %s updated", run_id, filename)

        run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
        logger.info("[%s] Files manually edited, re-planning...", run_id)

        background_tasks.add_task(_revalidate_and_replan, run_id, run.provider)
        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[%s] Failed to edit files: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to edit files: {str(e)}")


async def _revalidate_and_replan(run_id: str, provider: str):
    await workflow_engine.revalidate_and_replan(run_id, provider)


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str, background_tasks: BackgroundTasks):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot approve run in status: {run.status}")

    run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
    logger.info("[%s] Run approved by user", run_id)
    background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
    return run


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED]:
        raise HTTPException(status_code=400, detail=f"Cannot reject run in status: {run.status}")

    run = run_manager.update_run_status(run_id, RunStatus.FAILED, error="Rejected by user")
    logger.info("[%s] Run rejected by user", run_id)
    return run


@app.post("/runs/{run_id}/destroy", response_model=RunResponse)
async def destroy_run(run_id: str, background_tasks: BackgroundTasks):
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Cannot destroy run in status: {run.status}. Must be COMPLETED.")

    background_tasks.add_task(workflow_engine.execute_destroy_phase, run_id)
    run = run_manager.update_run_status(run_id, RunStatus.DESTROYING)
    logger.info("[%s] Destroy initiated by user", run_id)
    return run


# ============================================================================
# LLM CHAT HELPER (unchanged)
# ============================================================================

def _plan_chat_system_prompt(provider: str) -> str:
    p = (provider or "").lower()
    if p == "gcp":
        return "You are a helpful Terraform and Google Cloud expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."
    if p == "azure":
        return "You are a helpful Terraform and Microsoft Azure expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."
    if p == "digitalocean":
        return "You are a helpful Terraform and DigitalOcean expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."
    return "You are a helpful Terraform and AWS expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."


try:
    from langfuse.decorators import observe, langfuse_context

    @observe(name="chat_with_llm")
    async def _chat_with_llm(context: str, provider: str = "aws") -> str:
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(input=context, tags=["chat", "terraform_assistant"])

        return llm_generator.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": _plan_chat_system_prompt(provider)},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=600,
            model_override=config.GEMINI_MODEL_CHAT,
        )

except ImportError:
    async def _chat_with_llm(context: str, provider: str = "aws") -> str:
        return llm_generator.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": _plan_chat_system_prompt(provider)},
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=600,
            model_override=config.GEMINI_MODEL_CHAT,
        )


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "mode": "interactive",
        "providers": SUPPORTED_PROVIDERS,
    }


@app.get("/")
async def root():
    return {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "description": "Intelligent Terraform deployment with guided conversation (multi-cloud)",
        "conversation_workflow": {
            "1_start": "POST /conversations?owner=<>&repo=<>",
            "2_chat": "POST /conversations/{id}/message  (repeat until is_complete=true)",
            "3_generate": "POST /conversations/{id}/generate  → returns run_id",
            "4_monitor": "GET  /runs/{run_id}  (poll until PLANNED)",
            "5_review": "GET  /runs/{run_id}/files  or  POST /runs/{run_id}/chat",
            "6_deploy": "POST /runs/{run_id}/approve",
            "7_destroy": "POST /runs/{run_id}/destroy  (optional cleanup)",
        },
        "direct_workflow": {
            "1_create": "POST /runs",
            "2_monitor": "GET  /runs/{run_id}",
            "3_approve": "POST /runs/{run_id}/approve",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server on %s:%s", config.HOST, config.PORT)
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
