"""
FastAPI application - Main entry point (Async Interactive Workflow)
"""
import asyncio
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.models.schemas import AgentRequest, RunResponse, RunStatus, ChatRequest, ChatResponse
from app.services.run_manager import RunManager
from app.services.workflow_engine import WorkflowEngine
from app.services.llm_generator import LLMGenerator

# Setup logging
setup_logging(
    log_dir=config.LOGS_DIR,
    log_level="DEBUG" if config.DEBUG else "INFO"
)
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " - Interactive Workflow Edition",
    version=config.APP_VERSION,
    docs_url="/docs"
)

# Initialize services
run_manager = RunManager(base_dir=config.WORKSPACE_BASE_DIR)
workflow_engine = WorkflowEngine()
llm_generator = LLMGenerator()

# Log startup
logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
logger.info(f"Default Provider: {config.DEFAULT_PROVIDER.upper()}")
logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("🚀 Application started - Interactive Workflow Mode")
    logger.info(f"Supported providers: AWS, GCP")
    logger.info(f"Model Fallback: OpenAI -> Gemini")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Application shutting down")


@app.post("/runs", response_model=RunResponse, status_code=202)
async def create_run(request: AgentRequest, background_tasks: BackgroundTasks):
    """
    Create a new Terraform run (async).
    
    Returns immediately with run_id and status=CREATED.
    Background task starts the planning phase.
    """
    try:
        # Create run state
        run = run_manager.create_run(request)
        logger.info(f"[{run.run_id}] Created new {request.provider.upper()} run")
        
        # Schedule background planning task
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
    """
    Get the current state of a run.
    
    Poll this endpoint to track progress through the state machine.
    """
    run = run_manager.get_run(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    return run


@app.post("/runs/{run_id}/chat", response_model=ChatResponse)
async def chat_about_run(run_id: str, chat_request: ChatRequest):
    """
    Ask questions about the Terraform plan.
    
    Only available when status is PLANNED or REVIEWING.
    """
    run = run_manager.get_run(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Chat not available in status: {run.status}. Must be PLANNED or REVIEWING."
        )
    
    # Update status to REVIEWING if first chat
    if run.status == RunStatus.PLANNED:
        run_manager.update_run_status(run_id, RunStatus.REVIEWING)
    
    try:
        # Build context for LLM
        context = f"""
You are a helpful assistant explaining a Terraform plan to a user.

TERRAFORM PLAN:
{run.plan_output or "Plan not available"}

USER QUESTION: {chat_request.message}

Provide a clear, concise answer. If the user asks about costs, risks, or changes, explain based on the plan above.
"""
        
        # Call LLM (with fallback)
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
    
    # Update status to PLANNING
    run = run_manager.update_run_status(run_id, RunStatus.PLANNING)
    logger.info(f"[{run_id}] Run edit requested: {edit_request.message}")
    
    # Schedule background planning task with feedback
    background_tasks.add_task(
        workflow_engine.execute_planning_phase,
        run_id=run.run_id,
        request=None,
        feedback=edit_request.message
    )
    
    return run


@app.post("/runs/{run_id}/approve", response_model=RunResponse)
async def approve_run(run_id: str, background_tasks: BackgroundTasks):
    """
    Approve the plan and start terraform apply.
    
    Only available when status is PLANNED or REVIEWING.
    Transitions to APPROVED -> APPLYING -> COMPLETED.
    """
    run = run_manager.get_run(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve run in status: {run.status}"
        )
    
    # Update to APPROVED
    run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
    logger.info(f"[{run_id}] Run approved by user")
    
    # Schedule background apply task
    background_tasks.add_task(
        workflow_engine.execute_apply_phase,
        run_id
    )
    
    return run


@app.post("/runs/{run_id}/reject", response_model=RunResponse)
async def reject_run(run_id: str):
    """
    Reject/cancel a run.
    
    Transitions to FAILED status.
    """
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
    Transitions to DESTROYING -> DESTROYED.
    """
    run = run_manager.get_run(run_id)
    
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot destroy run in status: {run.status}. Must be COMPLETED."
        )
    
    # Schedule background destroy task
    background_tasks.add_task(
        workflow_engine.execute_destroy_phase,
        run_id
    )
    
    # Update status to indicate destroy has been initiated
    run = run_manager.update_run_status(run_id, RunStatus.DESTROYING)
    logger.info(f"[{run_id}] Destroy initiated by user")
    
    return run


from langfuse.decorators import observe, langfuse_context

@observe(name="chat_with_llm")
async def _chat_with_llm(context: str) -> str:
    """Helper to call LLM for chat (with fallback)"""
    
    # Add metadata
    if config.ENABLE_TRACING:
        langfuse_context.update_current_trace(
            input=context,
            tags=["chat", "terraform_assistant"]
        )

    try:
        # Try OpenAI first
        response = llm_generator.client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a helpful Terraform assistant."},
                {"role": "user", "content": context}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
        
    except Exception as e:
        logger.warning(f"OpenAI chat failed: {e}. Trying Gemini...")
        
        # Add metadata about fallback
        if config.ENABLE_TRACING:
            langfuse_context.update_current_trace(
                metadata={"fallback_triggered": True, "primary_error": str(e)}
            )
        
        # Fallback to Gemini
        try:
            content = llm_generator._call_gemini(
                "You are a helpful Terraform assistant.",
                context
            )
            return content
        except Exception as gemini_error:
            raise Exception(f"All LLM chat failed. OpenAI: {e}. Gemini: {gemini_error}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "providers": ["aws", "gcp"],
        "fallback": "openai -> gemini"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=config.DEBUG
    )
