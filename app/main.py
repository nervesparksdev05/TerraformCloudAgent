"""
FastAPI application - Main entry point (Unified)
README-driven multi-cloud Terraform generation with validation.

Aligned flow:
1) POST /conversations                — github_url (+ optional provider + github_token)
2) GET  /conversations/{id}/analyze   — fetch README + analyze (context + terraform_hints)
3) POST /conversations/{id}/message   — chat collects only critical missing inputs
4) POST /conversations/{id}/generate  — generate terraform files (LLM)
   - then validation runs in planning phase:
     terraform fmt, terraform validate, tflint
5) GET  /runs/{run_id}                — see plan_output incl. validation summary
6) POST /runs/{run_id}/edit           — update/refine (feedback-based)
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Header
from fastapi.responses import JSONResponse

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.models.schemas import (
    AgentRequest, RunResponse, RunStatus,
    ChatRequest, ChatResponse, TerraformBundle,
    FeedbackCreate, FeedbackResponse
)
from app.models.conversation_schemas import (
    ConversationCreateResponse,
    ChatMessageResponse,
)
from app.services.run_manager import RunManager
from app.services.workflow_engine import WorkflowEngine
from app.services.llm_generator import LLMGenerator
from app.services.conversation_manager import ConversationManager
from app.services.feedback_manager import feedback_manager

# Setup logging
setup_logging(
    log_dir=config.LOGS_DIR,
    log_level="DEBUG" if config.DEBUG else "INFO"
)
logger = get_logger(__name__)

# Initialize services (module-level)
run_manager = RunManager(base_dir=config.WORKSPACE_BASE_DIR)
workflow_engine = WorkflowEngine()
llm_generator = LLMGenerator()
conversation_manager = ConversationManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
    logger.info("Mode: README-Driven Deployment (multi-cloud)")
    logger.info("Default Provider: NONE (user may choose; chat can collect)")
    logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")
    logger.info("Supported providers: AWS, GCP, Azure, DigitalOcean")
    logger.info("Validations enabled: terraform fmt, terraform validate, tflint")

    try:
        yield
    finally:
        # Shutdown
        logger.info("Application shutting down")
        # Close async HTTP clients if your services expose close()
        try:
            # GitHubService uses httpx.AsyncClient; close if implemented
            if hasattr(conversation_manager, "github_service") and hasattr(conversation_manager.github_service, "close"):
                await conversation_manager.github_service.close()
        except Exception:
            pass


# Initialize FastAPI app (lifespan-based)
app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " - README-Driven Deployment (multi-cloud)",
    version=config.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan,
)

# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@app.post("/conversations", response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(request: Dict[str, Any]):
    """
    Start a new README-driven deployment session.

    Body:
    - github_url (required)
    - provider : aws|gcp|azure|digitalocean
    - github_token (optional): for private repos
    """
    try:
        github_url = request.get("github_url")
        if not github_url:
            raise HTTPException(status_code=400, detail="github_url is required")

        provider = request.get("provider")  
        github_token = request.get("github_token")

        result = conversation_manager.create_session(
            github_url=github_url,
            provider=provider,
            github_token=github_token
        )
        logger.info(f"Created README-driven session: {result['session_id']} for {github_url}")
        return ConversationCreateResponse(
            session_id=result["session_id"],
            bot_response=result["bot_response"],
            suggestions=result.get("suggestions", []),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{session_id}/analyze", response_model=ChatMessageResponse)
async def analyze_readme(session_id: str):
    """
    Fetch and analyze README from GitHub repository.

    This endpoint:
    1) Fetches README from GitHub
    2) Analyzes it with LLM to extract deployment requirements + terraform_hints
    3) Stores context in the session
    """
    try:
        response = await conversation_manager.analyze_readme(session_id)
        logger.info(f"[{session_id}] README analyzed successfully")
        return response
    except Exception as e:
        logger.error(f"[{session_id}] README analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/message", response_model=ChatMessageResponse)
async def send_message(session_id: str, request: Dict[str, Any]):
    """
    Chat with the deployment assistant.
    Collects only critical missing inputs (provider, region/location, env, ssh cidrs, etc).
    """
    try:
        message = request.get("message")
        if not message:
            raise HTTPException(status_code=400, detail="message is required")

        response = await conversation_manager.send_message(session_id, message)
        logger.info(f"[{session_id}] Message processed: {message[:50]}...")

        return ChatMessageResponse(
            session_id=session_id,
            bot_response=response["bot_response"],
            suggestions=response.get("suggestions", []),
            collected_parameters=response["collected_parameters"],
            is_complete=response["is_complete"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{session_id}] Message processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{session_id}")
async def get_conversation(session_id: str):
    """Get session state: history + collected parameters + completion."""
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")
    return session.dict()


@app.get("/sessions")
async def list_sessions(limit: int = 20):
    """List recent conversation sessions for history."""
    try:
        return conversation_manager.list_sessions(limit=limit)
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
        raise HTTPException(status_code=404, detail="Session not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{session_id}/generate", response_model=RunResponse, status_code=202)
async def generate_terraform_from_conversation(session_id: str, background_tasks: BackgroundTasks):
    """
    Generate Terraform configuration from a completed conversation.

    Prerequisite:
    - session.is_complete must be true (chat collected minimum inputs)
    """
    try:
        session = conversation_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")

        if not session.is_complete:
            raise HTTPException(
                status_code=400,
                detail="Conversation is not complete. Continue chatting until the bot says you can generate Terraform."
            )

        terraform_params = conversation_manager.build_terraform_request(session_id)
        logger.info(f"[{session_id}] Built Terraform params (aligned): {terraform_params}")

        agent_request = AgentRequest(
            request=terraform_params,
            provider=(terraform_params.get("provider") or session.provider),
            auto_approve=False
        )

        run = run_manager.create_run(agent_request)
        run.metadata = {
            "conversation_params": conversation_manager.get_collected_parameters(session_id),
            "session_id": session_id,
        }
        run_manager.save_run_state(run.run_id, run)

        conversation_manager.add_run_to_session(session_id, run.run_id)

        logger.info(f"[{session_id}] Creating run {run.run_id} from conversation")

        # Planning phase generates files and runs validations (fmt/validate/tflint)
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
    """Create a new Terraform run (direct mode)."""
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
    """Ask questions about the generated files / plan_output."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Chat not available in status: {run.status}")

    if run.status == RunStatus.PLANNED:
        run_manager.update_run_status(run_id, RunStatus.REVIEWING)

    try:
        context = (
            "Explain the generated Terraform files and validations briefly.\n\n"
            f"PLAN/VALIDATION OUTPUT:\n{run.plan_output or 'Not available'}\n\n"
            f"QUESTION: {chat_request.message}"
        )
        response_text = await _chat_with_llm(context)
        return ChatResponse(response=response_text, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.error(f"[{run_id}] Chat failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat failed: {str(e)}")


@app.post("/runs/{run_id}/edit", response_model=RunResponse)
async def edit_run(run_id: str, edit_request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Update feature: refine Terraform based on feedback.
    Uses existing LLMGenerator.refine_terraform flow.
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit run in status: {run.status}")

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
    """Get generated Terraform files."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    try:
        workspace_path = run_manager.get_workspace_path(run_id)
        files: Dict[str, str] = {}

        for fname in ["main.tf", "variables.tf", "outputs.tf"]:
            p = workspace_path / fname
            if p.exists():
                files[fname] = p.read_text(encoding="utf-8")

        if not files:
            raise HTTPException(status_code=500, detail="Terraform files not found in workspace")

        return {"run_id": run_id, "files": files, "timestamp": datetime.now().isoformat()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{run_id}] Failed to read files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to read files: {str(e)}")


@app.post("/runs/{run_id}/files", response_model=RunResponse)
async def edit_run_files(run_id: str, files: dict, background_tasks: BackgroundTasks):
    """Manual edit: write files then revalidate + replan."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot edit files in status: {run.status}")

    if "main_tf" not in files:
        raise HTTPException(status_code=400, detail="main_tf is required.")

    try:
        workspace_path = run_manager.get_workspace_path(run_id)

        for file_key, filename in [("main_tf", "main.tf"), ("variables_tf", "variables.tf"), ("outputs_tf", "outputs.tf")]:
            if file_key in files:
                (workspace_path / filename).write_text(files[file_key], encoding="utf-8")
                logger.debug(f"[{run_id}] {filename} updated")

        run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
        background_tasks.add_task(_revalidate_and_replan, run_id, run.provider)
        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[{run_id}] Failed to edit files: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to edit files: {str(e)}")


async def _revalidate_and_replan(run_id: str, provider: str):
    await workflow_engine.revalidate_and_replan(run_id, provider)


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str, background_tasks: BackgroundTasks):
    """Approve and apply."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(status_code=400, detail=f"Cannot approve run in status: {run.status}")

    run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
    background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
    return run


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str):
    """Reject/cancel a run."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED]:
        raise HTTPException(status_code=400, detail=f"Cannot reject run in status: {run.status}")

    return run_manager.update_run_status(run_id, RunStatus.FAILED, error="Rejected by user")


@app.post("/runs/{run_id}/destroy", response_model=RunResponse)
async def destroy_run(run_id: str, background_tasks: BackgroundTasks):
    """Destroy infra (only when COMPLETED)."""
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail=f"Cannot destroy run in status: {run.status}. Must be COMPLETED.")

    background_tasks.add_task(workflow_engine.execute_destroy_phase, run_id)
    return run_manager.update_run_status(run_id, RunStatus.DESTROYING)


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
        response = llm_generator.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful Terraform expert. Answer questions briefly and accurately. "
                        "Explain validations (fmt/validate/tflint) if present."
                    ),
                },
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content

except ImportError:
    async def _chat_with_llm(context: str) -> str:
        response = llm_generator.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful Terraform expert. Answer questions briefly and accurately. "
                        "Explain validations (fmt/validate/tflint) if present."
                    ),
                },
                {"role": "user", "content": context},
            ],
            temperature=0.3,
            max_tokens=600,
        )
        return response.choices[0].message.content


# ============================================================================
# UTILITY ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "mode": "readme_driven",
        "providers": ["aws", "gcp", "azure", "digitalocean"],
        "validations": ["terraform fmt", "terraform validate", "tflint"],
    }


@app.get("/")
async def root():
    return {
        "app": config.APP_NAME,
        "version": config.APP_VERSION,
        "description": "Intelligent multi-cloud Terraform deployment with README-driven conversation",
        "conversation_workflow": {
            "1_start": "POST /conversations (github_url required; provider optional)",
            "2_analyze": "GET  /conversations/{id}/analyze",
            "3_chat": "POST /conversations/{id}/message (until is_complete=true)",
            "4_generate": "POST /conversations/{id}/generate → run_id",
            "5_monitor": "GET  /runs/{run_id} (poll until PLANNED)",
            "6_review": "GET  /runs/{run_id}/files  or  POST /runs/{run_id}/chat",
            "7_update": "POST /runs/{run_id}/edit (feedback)",
            "8_apply": "POST /runs/{run_id}/approve",
            "9_destroy": "POST /runs/{run_id}/destroy (optional)",
        },
        "docs": "/docs"
    }


# ============================================================================
# FEEDBACK ENDPOINTS
# ============================================================================

async def verify_admin_api_key(x_admin_api_key: Optional[str] = Header(None)):
    if x_admin_api_key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid Admin API Key")
    return x_admin_api_key


@app.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(feedback: FeedbackCreate):
    try:
        return feedback_manager.submit_feedback(feedback)
    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/feedback", response_model=List[FeedbackResponse])
async def get_feedback(limit: int = 100, api_key: str = Depends(verify_admin_api_key)):
    try:
        return feedback_manager.get_all_feedback(limit)
    except Exception as e:
        logger.error(f"Failed to fetch feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
