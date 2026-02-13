"""
FastAPI application - Main entry point (Unified)
Supports both direct execution and interactive workflow modes
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.models.schemas import (
    AgentRequest, RunResponse, RunStatus,
    ChatRequest, ChatResponse, TerraformBundle
)
from app.models.conversation_schemas import (
    ConversationCreateResponse,
    ChatMessage,
    ChatMessageResponse,
    TerraformGenerationRequest
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
logger.info(f"Mode: Interactive Workflow")
logger.info(f"Default Provider: {config.DEFAULT_PROVIDER.upper()}")
logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Application started - Interactive Workflow Mode")
    logger.info("Supported providers: AWS, GCP, Azure, DigitalOcean")
    logger.info("Human-in-the-loop deployment with review, chat, and approval")
    yield
    # Shutdown
    logger.info("Application shutting down")

# Initialize FastAPI app with lifespan
app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " - Interactive Workflow",
    version=config.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan
)


# ============================================================================
# CONVERSATION ENDPOINTS (Multi-turn intelligent parameter collection)
# ============================================================================

@app.post("/conversations", response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(provider: str = "aws", github_url: str = "", github_token: str = ""):
    """
    Start a new intelligent conversational session for infrastructure deployment.

    The bot will guide the user through every required parameter — compute,
    storage, networking, security, IAM, monitoring — step by step.

    Workflow:
    1. POST /conversations              — Start (returns session_id + greeting)
    2. POST /conversations/{id}/message — Chat until is_complete=true
    3. POST /conversations/{id}/generate — Generate Terraform → returns run_id
    4. GET  /runs/{run_id}              — Poll until PLANNED
    5. POST /runs/{run_id}/approve      — Deploy
    """
    try:
        result = await conversation_manager.create_session(provider=provider, github_url=github_url, github_token=github_token)
        logger.info(f"Created conversation session: {result['session_id']}")
        return ConversationCreateResponse(
            session_id=result["session_id"],
            bot_response=result["bot_response"],
            suggestions=result.get("suggestions", []),
        )
    except Exception as e:
        logger.error(f"Failed to create conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/message", response_model=ChatMessageResponse)
async def send_message(session_id: str, chat_message: ChatMessage, background_tasks: BackgroundTasks):
    """
    Send a message in an active conversation.

    The bot will:
    - Understand plain English — no cloud knowledge required
    - Extract all parameters from your answers
    - Provide smart quick-reply suggestions after every response
    - Pick the best option if you say "you choose" or "I don't know"
    - Signal completion when all required parameters are collected
    - **Automatically generate Terraform files when complete**

    Examples:
    - "I want to deploy an AWS S3 bucket"
    - "GCP virtual machine for production"
    - "You choose for me"
    - "Use us-east-1"
    """
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation session {session_id} not found"
            )

        response = await conversation_manager.process_message(
            session_id=session_id,
            user_message=chat_message.message
        )

        # Auto-generate Terraform when conversation completes
        if response.is_complete:
            try:
                request_text = conversation_manager.build_terraform_request(session_id)
                logger.info(f"[{session_id}] Auto-generating Terraform. Request:\n{request_text}")
                
                agent_request = AgentRequest(
                    request=request_text,
                    provider=session.provider,
                    auto_approve=False
                )
                
                run = run_manager.create_run(agent_request)
                run.metadata = {
                    "conversation_params": conversation_manager.get_collected_parameters(session_id),
                    "session_id": session_id,
                }
                run_manager.save_run_state(run.run_id, run)
                
                # Trigger workflow in background
                background_tasks.add_task(
                    workflow_engine.execute_planning_phase,
                    run.run_id,
                    agent_request
                )
                
                response.run_id = run.run_id
                logger.info(f"[{session_id}] Terraform generation started: run_id={run.run_id}")
                
            except Exception as e:
                logger.error(f"[{session_id}] Failed to auto-generate Terraform: {str(e)}")
                # Don't fail the whole request, just log the error

        logger.debug(f"[{session_id}] Message processed (complete: {response.is_complete})")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{session_id}] Failed to process message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    """
    Get the current state of a conversation session.

    Returns full conversation history, collected parameters, and completion status.
    """
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation session {session_id} not found"
        )
    return session.dict()


@app.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent conversation sessions for the sidebar history."""
    try:
        sessions = conversation_manager.list_sessions(limit=limit)
        return sessions
    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a conversation session."""
    try:
        success = conversation_manager.delete_session(session_id)
        if success:
            return {"message": "Session deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Session not found")
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/generate", response_model=RunResponse, status_code=202)
async def generate_terraform_from_conversation(
    session_id: str,
    background_tasks: BackgroundTasks
):
    """
    Generate Terraform configuration from a completed conversation.

    Prerequisites:
    - Conversation must be complete (is_complete = true)

    This endpoint:
    1. Builds a rich structured Terraform request from collected parameters
    2. Creates a run (identical to POST /runs)
    3. Returns run_id for tracking

    After this, follow the normal run workflow:
    - GET  /runs/{run_id}         — poll for PLANNED status
    - POST /runs/{run_id}/approve — deploy
    """
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation session {session_id} not found"
            )

        if not session.is_complete:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Conversation is not complete yet. "
                    "Continue chatting until the bot confirms all parameters are collected."
                )
            )

        # Build structured params from conversation (returns Dict for fast generation)
        terraform_params = conversation_manager.build_terraform_request(session_id)
        logger.info(f"[{session_id}] Built Terraform params: {terraform_params}")

        agent_request = AgentRequest(
            request=terraform_params,  # Pass Dict of params for fast structured generation
            provider=session.provider,
            auto_approve=False
        )

        # Create run and persist conversation params as metadata
        run = run_manager.create_run(agent_request)
        run.metadata = {
            "conversation_params": conversation_manager.get_collected_parameters(session_id),
            "session_id": session_id,
        }
        run_manager.save_run_state(run.run_id, run)
        
        # Link run to session
        conversation_manager.add_run_to_session(session_id, run.run_id)

        logger.info(f"[{session_id}] Creating run {run.run_id} from conversation")

        background_tasks.add_task(
            workflow_engine.execute_planning_phase,
            run.run_id,
            agent_request
        )

        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{session_id}] Failed to generate Terraform: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STANDARD RUN ENDPOINTS (Direct Terraform generation)
# ============================================================================

@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(request: AgentRequest, background_tasks: BackgroundTasks):
    """
    Create a new Terraform run with human-in-the-loop review.

    Returns immediately with run_id and status=CREATED.

    Workflow:
    1. POST /runs                   — Create run (CREATED)
    2. GET  /runs/{run_id}          — Poll until PLANNED
    3. POST /runs/{run_id}/chat     — Ask questions (optional)
    4. POST /runs/{run_id}/edit     — Request changes (optional)
    5. POST /runs/{run_id}/approve  — Deploy
    6. POST /runs/{run_id}/destroy  — Tear down (optional)
    """
    try:
        run = run_manager.create_run(request)
        logger.info(f"[{run.run_id}] Created new {request.provider.upper()} run")
        background_tasks.add_task(
            workflow_engine.execute_planning_phase,
            run.run_id,
            request
        )
        return run
    except Exception as e:
        logger.error(f"Failed to create run: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get the current state of a run."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@app.post("/runs/{run_id}/chat", response_model=ChatResponse)
async def chat_about_run(run_id: str, chat_request: ChatRequest):
    """
    Ask questions about the Terraform plan.

    Only available when status is PLANNED or REVIEWING.

    Examples:
    - "What resources will be created?"
    - "How much will this cost per month?"
    - "Is this secure?"
    - "What's the purpose of the NAT gateway?"
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Chat not available in status: {run.status}. Must be PLANNED or REVIEWING."
        )

    if run.status == RunStatus.PLANNED:
        run_manager.update_run_status(run_id, RunStatus.REVIEWING)

    try:
        context = (
            f"Explain the Terraform plan briefly and clearly.\n\n"
            f"PLAN:\n{run.plan_output or 'Plan not available'}\n\n"
            f"QUESTION: {chat_request.message}"
        )
        response_text = await _chat_with_llm(context)
        return ChatResponse(
            response=response_text,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        logger.error(f"[{run_id}] Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/runs/{run_id}/edit", response_model=RunResponse)
async def edit_run(run_id: str, edit_request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Refine the Terraform plan based on user feedback.

    Only available when status is PLANNED or REVIEWING.
    Transitions back to PLANNING.
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit run in status: {run.status}. Must be PLANNED or REVIEWING."
        )

    run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
    logger.info(f"[{run_id}] Run edit requested: {edit_request.message}")

    background_tasks.add_task(
        workflow_engine.execute_planning_phase,
        run_id=run.run_id,
        request=None,
        feedback=edit_request.message
    )
    return run


@app.get("/runs/{run_id}/files")
async def get_run_files(run_id: str):
    """
    Get the generated Terraform files for review.

    Returns the actual .tf files (main.tf, variables.tf, outputs.tf).
    Files are available as soon as they're generated, regardless of plan status.
    """
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

        logger.info(f"[{run_id}] Files retrieved for review")
        return {"run_id": run_id, "files": files, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logger.error(f"[{run_id}] Failed to read files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read files: {str(e)}")


@app.post("/runs/{run_id}/files", response_model=RunResponse)
async def edit_run_files(run_id: str, files: dict, background_tasks: BackgroundTasks):
    """
    Edit Terraform files directly (advanced users).

    Security validation is always re-run after manual edits.
    Only available when status is PLANNED or REVIEWING.
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit files in status: {run.status}. Must be PLANNED or REVIEWING."
        )

    if "main_tf" not in files:
        raise HTTPException(status_code=400, detail="main_tf is required.")

    try:
        workspace_path = run_manager.get_workspace_path(run_id)

        for file_key, filename in [("main_tf", "main.tf"), ("variables_tf", "variables.tf"), ("outputs_tf", "outputs.tf")]:
            if file_key in files:
                (workspace_path / filename).write_text(files[file_key], encoding="utf-8")
                logger.debug(f"[{run_id}] {filename} updated")

        run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
        logger.info(f"[{run_id}] Files manually edited, re-planning...")

        background_tasks.add_task(_revalidate_and_replan, run_id, run.provider)
        return run

    except Exception as e:
        logger.error(f"[{run_id}] Failed to edit files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to edit files: {str(e)}")


async def _revalidate_and_replan(run_id: str, provider: str):
    await workflow_engine.revalidate_and_replan(run_id, provider)


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str, background_tasks: BackgroundTasks):
    """
    Approve the plan and start terraform apply.
    Only available when status is PLANNED or REVIEWING.
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve run in status: {run.status}"
        )

    run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
    logger.info(f"[{run_id}] Run approved by user")
    background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
    return run


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str):
    """Reject/cancel a run."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reject run in status: {run.status}"
        )

    run = run_manager.update_run_status(run_id, RunStatus.FAILED, error="Rejected by user")
    logger.info(f"[{run_id}] Run rejected by user")
    return run


@app.post("/runs/{run_id}/destroy", response_model=RunResponse)
async def destroy_run(run_id: str, background_tasks: BackgroundTasks):
    """
    Destroy infrastructure created by this run.
    Only available when status is COMPLETED.
    ⚠️ WARNING: This will delete all resources!
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot destroy run in status: {run.status}. Must be COMPLETED."
        )

    background_tasks.add_task(workflow_engine.execute_destroy_phase, run_id)
    run = run_manager.update_run_status(run_id, RunStatus.DESTROYING)
    logger.info(f"[{run_id}] Destroy initiated by user")
    return run


# ============================================================================
# LLM CHAT HELPER
# ============================================================================

try:
    from langfuse.decorators import observe, langfuse_context

    @observe(name="chat_with_llm")
    async def _chat_with_llm(context: str) -> str:
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(
                input=context,
                tags=["chat", "terraform_assistant"]
            )
        response_content = llm_generator.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful Terraform and AWS expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."},
                {"role": "user", "content": context}
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response_content

except ImportError:
    async def _chat_with_llm(context: str) -> str:
        response_content = llm_generator.llm_service.chat_completion(
            messages=[
                {"role": "system", "content": "You are a helpful Terraform and AWS expert. Answer questions about Terraform plans briefly, clearly, and accurately. Use plain language."},
                {"role": "user", "content": context}
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response_content


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "mode": "interactive",
        "providers": ["aws"],
    }


@app.get("/")
async def root():
    return {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "description": "Intelligent AWS Terraform deployment with guided conversation",
        "conversation_workflow": {
            "1_start":    "POST /conversations",
            "2_chat":     "POST /conversations/{id}/message  (repeat until is_complete=true)",
            "3_generate": "POST /conversations/{id}/generate  → returns run_id",
            "4_monitor":  "GET  /runs/{run_id}  (poll until PLANNED)",
            "5_review":   "GET  /runs/{run_id}/files  or  POST /runs/{run_id}/chat",
            "6_deploy":   "POST /runs/{run_id}/approve",
            "7_destroy":  "POST /runs/{run_id}/destroy  (optional cleanup)",
        },
        "direct_workflow": {
            "1_create":  "POST /runs",
            "2_monitor": "GET  /runs/{run_id}",
            "3_approve": "POST /runs/{run_id}/approve",
        },
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )