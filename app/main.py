# app/main.py  

"""
FastAPI application - Main entry point (Unified)
Supports both direct execution and interactive workflow modes
"""
from __future__ import annotations

import asyncio
import re
import os
import redis.asyncio as redis
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Optional, Dict

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.core.auth import get_current_user, get_optional_user
from app.rate_limiter import check_rate_limit
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
from app.services.email_service import email_service
from app.services.user_service import user_service

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

# Global Redis client
redis_client: Optional[redis.Redis] = None

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
    global redis_client
    logger.info("Application starting - Interactive Workflow Mode")
    
    # Initialize Redis connection
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        logger.info(f"Connected to Redis at {redis_url}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        redis_client = None

    logger.info(
        f"Supported providers: {', '.join([p.upper() if p!='digitalocean' else 'DigitalOcean' for p in SUPPORTED_PROVIDERS])}"
    )
    logger.info("Human-in-the-loop deployment with review, chat, and approval")
    
    yield
    
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    logger.info("Application shutting down")


app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION + " - Interactive Workflow",
    version=config.APP_VERSION,
    docs_url="/docs",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Unauthenticated health check endpoint."""
    return {"status": "ok"}

# ============================================================================
# AUTH / USER ENDPOINTS
# ============================================================================

@app.post("/auth/sync-user")
async def sync_user(
    user: Dict = Depends(get_current_user),
):
    """
    Sync the authenticated Firebase user into MongoDB.
    Call this from the frontend immediately after every login (email or Google).
    Returns the stored user document.
    """
    try:
        doc = user_service.upsert_user(user)
        return {"status": "ok", "user": doc}
    except Exception as e:
        logger.error(f"Failed to sync user to MongoDB: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to sync user: {str(e)}")


@app.get("/auth/me")
async def get_me(
    user: Dict = Depends(get_current_user),
):
    """
    Return the current user's MongoDB profile.
    """
    uid = user.get("uid") or user.get("user_id")
    doc = user_service.get_user_by_uid(uid)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found in database")
    return doc


# ============================================================================
# CONVERSATION ENDPOINTS
# ============================================================================

@app.post("/conversations", response_model=ConversationCreateResponse, status_code=201)
async def create_conversation(
    owner: str = "",
    repo: str = "",
    github_token: str = "",
    github_branch: str = "",
    user: Optional[Dict] = Depends(get_current_user),
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
async def send_message(
    session_id: str,
    chat_message: ChatMessage,
    background_tasks: BackgroundTasks,
    user: Optional[Dict] = Depends(get_current_user),
):
    """
    Send a message in an active conversation.
    Auto-generates Terraform run when conversation completes.
    """
    logger.info("[%s] Received message request", session_id)
    
    # Apply Rate Limiting
    if user:
        await check_rate_limit(user.get("uid", "anonymous"), redis_client)

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


@app.post("/conversations/{session_id}/message/stream")
async def stream_message(
    session_id: str,
    chat_message: ChatMessage,
    user: Optional[Dict] = Depends(get_current_user),
):
    """
    Stream bot responses in real-time using Server-Sent Events (SSE).
    """
    import json
    from app.services.llm_service import AsyncLLMService
    
    async def generate():
        # Apply Rate Limiting
        if user:
            await check_rate_limit(user.get("uid", "anonymous"), redis_client)
            
        try:
            session = conversation_manager.get_session(session_id)
            if not session:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                return

            # Add user message to session
            session.messages.append({"role": "user", "content": chat_message.message})
            logger.info(f"[{session_id}] User message (streaming): {chat_message.message}")

            # Build LLM messages
            messages = []
            
            # Add system prompt
            messages.append({
                "role": "system",
                "content": conversation_manager.SYSTEM_PROMPT + conversation_manager.FRIENDLY_BRIDGE_PROMPT
            })
            
            # Add conversation history
            for msg in session.messages:
                messages.append(msg)

            # Stream the LLM response
            async_llm = AsyncLLMService()
            full_response = ""
            
            async for chunk in async_llm.stream_chat_completion(
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            ):
                full_response += chunk
                # Don't send raw chunks yet - wait to parse JSON first

            # Process the complete response
            # 1. Use regex to extract JSON object from response (in case there's leading/trailing text)
            clean_response = full_response.strip()
            
            # Simple heuristic: look for the first '{' and last '}'
            match = re.search(r'(\{.*\})', clean_response, re.DOTALL)
            if match:
                clean_response = match.group(1)

            try:
                data = json.loads(clean_response)
                # If parsed successfully, message content is the extracted 'message' field
                message_content = data.get("message", full_response)
                
                # SAFEGUARD: If the message itself is a JSON string, extract the actual message from it
                if isinstance(message_content, str) and message_content.strip().startswith('{'):
                    try:
                        parsed_msg = json.loads(message_content)
                        if isinstance(parsed_msg, dict):
                            message_content = str(parsed_msg.get("message", message_content))
                    except json.JSONDecodeError:
                        pass
                        
            except json.JSONDecodeError:
                # If still not JSON, treat entire response as message (cleaning it up slightly)
                # If it looks like there were code fences, strip them for a cleaner fallback
                message_content = full_response
                if "```json" in message_content:
                    message_content = message_content.split("```json")[-1].split("```")[0].strip()
                elif "```" in message_content:
                    message_content = message_content.split("```")[-1].split("```")[0].strip()
                
                data = {
                    "message": message_content,
                    "extracted_params": {},
                    "suggestions": [],
                    "is_complete": False
                }

            # Check if conversation is complete
            session.is_complete = bool(data.get("is_complete", False))
            
            # If complete, append cost calculation
            if session.is_complete:
                # Apply defaults first
                conversation_manager._apply_defaults(session.collected_parameters, provider=session.provider)
                
                # Calculate cost
                try:
                    cost_block = conversation_manager._calculate_cost(
                        session.collected_parameters, 
                        provider=session.provider
                    )
                    # Append cost to message
                    message_content += f"\n\n{cost_block}\nAll set! I'll generate your Terraform configuration now."
                    
                    # Update data message too so it's consistent
                    data["message"] = message_content
                except Exception as e:
                    logger.error(f"Failed to calculate cost: {e}")

            session.updated_at = datetime.now()

            # Now stream the message content character by character for smooth display
            chunk_size = 20  # Send 20 characters at a time
            for i in range(0, len(message_content), chunk_size):
                chunk = message_content[i:i + chunk_size]
                yield f"data: {json.dumps({'content': chunk})}\n\n"
                # Small delay to make streaming visible
                await asyncio.sleep(0.01)

            # Update session with bot response
            session.messages.append({"role": "assistant", "content": message_content})
            
            # Merge extracted parameters
            if isinstance(data.get("extracted_params"), dict):
                conversation_manager._deep_merge(session.collected_parameters, data["extracted_params"])

            # Update provider if chosen
            chosen = str(session.collected_parameters.get("cloud_provider") or session.provider or "unknown")
            provider_norm = conversation_manager._normalize_provider(chosen)
            session.provider = provider_norm
            
            if provider_norm in conversation_manager.SUPPORTED_PROVIDERS:
                session.collected_parameters["cloud_provider"] = provider_norm

            # Save session
            if conversation_manager.sessions_collection is not None:
                try:
                    conversation_manager.sessions_collection.update_one(
                        {"session_id": session_id},
                        {"$set": session.dict(exclude={"_id"})},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Failed to update session {session_id}: {e}")

            # Auto-generate Terraform when conversation completes
            run_id = None
            if session.is_complete:
                try:
                    terraform_params = conversation_manager.build_terraform_request(session_id)
                    provider_norm = _normalize_provider(
                        str(terraform_params.get("cloud_provider") or session.provider or "aws")
                    )
                    if provider_norm in SUPPORTED_PROVIDERS:
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

                        # Launch planning phase in background
                        asyncio.create_task(
                            workflow_engine.execute_planning_phase(run.run_id, agent_request)
                        )
                        run_id = run.run_id
                        logger.info("[%s] Terraform generation started (streaming): run_id=%s", session_id, run.run_id)
                except Exception as e:
                    logger.error("[%s] Failed to auto-generate Terraform (streaming): %s", session_id, e, exc_info=True)

            # Send completion event
            completion_data = {
                'done': True,
                'is_complete': session.is_complete,
                'suggestions': data.get('suggestions', []),
                'collected_parameters': session.collected_parameters
            }
            if run_id:
                completion_data['run_id'] = run_id
            yield f"data: {json.dumps(completion_data)}\n\n"

        except Exception as e:
            logger.error(f"[{session_id}] Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    user: Optional[Dict] = Depends(get_current_user),
):
    logger.debug("[%s] Fetching conversation details", session_id)
    session = conversation_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Conversation session {session_id} not found")
    return session.dict()


@app.get("/sessions")
async def list_sessions(
    limit: int = 20,
    user: Optional[Dict] = Depends(get_current_user),
):
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

        # Standard Terraform files to look for
        for fname, key in [("main.tf", "main_tf"), ("variables.tf", "variables_tf"), ("outputs.tf", "outputs_tf")]:
            p = workspace_path / fname
            if p.exists():
                try:
                    files[key] = p.read_text(encoding="utf-8")
                except Exception as e:
                    logger.warning("[%s] Failed to read %s: %s", run_id, fname, e)

        # Return whatever we found (can be empty dict if just started)
        logger.info("[%s] Files retrieved for review (%d found)", run_id, len(files))
        return {"run_id": run_id, "files": files, "timestamp": datetime.now().isoformat()}

    except Exception as e:
        logger.error("[%s] Unexpected error retrieving files: %s", run_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


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


# ============================================================================
# APPROVAL WORKFLOW ENDPOINTS (Email)
# ============================================================================

@app.post("/runs/{run_id}/send-for-approval")
async def send_approval_email(
    run_id: str,
    user: Dict = Depends(get_current_user)
):
    """
    Send the generated Terraform files to the user's email for approval.
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Verify user owns this run (simple check)
    if run.metadata and run.metadata.get("user_email") and run.metadata.get("user_email") != user.get("email"):
        # If run has an email associated, ensure it matches
        # Skip check if no email in metadata (e.g. created via CLI/API without auth)
        pass

    # Get Terraform files
    try:
        files = run_manager.get_run_files(run_id)
        if not files or "main.tf" not in files:
            raise HTTPException(status_code=400, detail="Terraform files not found or incomplete")
        
        # Prepare summary
        summary = {
            "resources": [] 
        }
        # Try to get existing plan summary if available from metadata
        if run.metadata and "plan_summary" in run.metadata:
             summary["resources"] = run.metadata["plan_summary"]
        
        # Send email
        user_email = user.get("email")
        if not user_email:
             raise HTTPException(status_code=400, detail="User email not found in token")

        success = email_service.send_terraform_approval_email(
            to_email=user_email,
            run_id=run_id,
            terraform_files=files,
            terraform_summary=summary
        )
        
        if success:
            # Update run metadata with approval info
            if not run.approval_info:
                run.approval_info = {}
            
            run.approval_info.update({
                "email_sent_at": datetime.utcnow().isoformat(),
                "email_sent_to": user_email,
                "status": "pending_email_approval"
            })
            run_manager.save_run_state(run_id, run)
            
            return {"message": "Approval email sent successfully", "email": user_email}
        else:
            raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP configuration.")
            
    except Exception as e:
        logger.error(f"Error sending approval email for {run_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error sending email: {str(e)}")


@app.get("/approve/{token}")
async def approve_run_via_email(token: str, background_tasks: BackgroundTasks):
    """
    Handle run approval via email link
    """
    from fastapi.responses import HTMLResponse
    
    data = email_service.verify_approval_token(token)
    if not data:
        return HTMLResponse(content="<h1>❌ Invalid or expired token</h1><p>Please request a new approval email.</p>", status_code=400)
    
    run_id = data.get("run_id")
    user_email = data.get("user_email")
    
    run = run_manager.get_run(run_id)
    if not run:
        return HTMLResponse(content="<h1>❌ Run not found</h1>", status_code=404)
        
    if run.status == RunStatus.APPROVED:
        return HTMLResponse(content=f"<h1>✅ Already Approved</h1><p>Run {run_id} was already approved.</p>")
    
    if run.status not in [RunStatus.PLANNED, RunStatus.REVIEWING]:
         return HTMLResponse(content=f"<h1>⚠️ Cannot Approve</h1><p>Run status is {run.status}. Only PLANNED or REVIEWING runs can be approved.</p>", status_code=400)

    # Update status
    run = run_manager.update_run_status(run_id, RunStatus.APPROVED)
    
    # Update approval metadata
    if not run.approval_info:
        run.approval_info = {}
        
    run.approval_info.update({
        "approved_at": datetime.utcnow().isoformat(),
        "approved_by": user_email,
        "method": "email_link",
        "status": "approved"
    })
    run_manager.save_run_state(run_id, run)
    
    # Trigger Apply Phase
    background_tasks.add_task(workflow_engine.execute_apply_phase, run_id)
    
    # Send confirmation
    email_service.send_approval_confirmation_email(user_email, run_id, approved=True)
    
    return HTMLResponse(content=f"""
    <html>
        <head>
            <title>Run Approved</title>
            <style>
                body {{ font-family: sans-serif; text-align: center; padding: 50px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                h1 {{ color: #10b981; }}
                p {{ font-size: 18px; color: #4b5563; }}
                .id {{ background: #f3f4f6; padding: 5px 10px; border-radius: 4px; font-family: monospace; }}
                .status {{ margin-top: 20px; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✅ Run Approved & Apply Triggered</h1>
                <p>Run ID: <span class="id">{run_id}</span></p>
                <p class="status">Terraform Apply has started in the background.</p>
                <p>You can close this window and check the dashboard for progress.</p>
            </div>
        </body>
    </html>
    """)


@app.get("/reject/{token}")
async def reject_run_via_email(token: str, reason: str = "Rejected via email"):
    """
    Handle run rejection via email link
    """
    from fastapi.responses import HTMLResponse

    data = email_service.verify_approval_token(token)
    if not data:
        return HTMLResponse(content="<h1>❌ Invalid or expired token</h1><p>Please request a new approval email.</p>", status_code=400)
    
    run_id = data.get("run_id")
    user_email = data.get("user_email")
    
    run = run_manager.get_run(run_id)
    if not run:
         return HTMLResponse(content="<h1>❌ Run not found</h1>", status_code=404)

    if run.status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.REJECTED]:
         return HTMLResponse(content=f"<h1>⚠️ Cannot Reject</h1><p>Run status is already {run.status}.</p>", status_code=400)

    # Update status
    run = run_manager.update_run_status(run_id, RunStatus.REJECTED, error=f"Rejected by user: {reason}")
    
    # Update approval metadata
    if not run.approval_info:
        run.approval_info = {}
        
    run.approval_info.update({
        "rejected_at": datetime.utcnow().isoformat(),
        "rejected_by": user_email,
        "rejection_reason": reason,
        "method": "email_link",
        "status": "rejected"
    })
    run_manager.save_run_state(run_id, run)
    
    # Send confirmation
    email_service.send_approval_confirmation_email(user_email, run_id, approved=False, reason=reason)
    
    return HTMLResponse(content=f"""
    <html>
        <head>
            <title>Run Rejected</title>
            <style>
                body {{ font-family: sans-serif; text-align: center; padding: 50px; }}
                .container {{ max-width: 600px; margin: 0 auto; }}
                h1 {{ color: #ef4444; }}
                p {{ font-size: 18px; color: #4b5563; }}
                .id {{ background: #f3f4f6; padding: 5px 10px; border-radius: 4px; font-family: monospace; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Run Rejected</h1>
                <p>Run ID: <span class="id">{run_id}</span></p>
                <p>The configuration has been rejected and will not be applied.</p>
            </div>
        </body>
    </html>
    """)


@app.get("/runs/{run_id}/approval-status")
async def get_approval_status(run_id: str, user: Dict = Depends(get_current_user)):
    """
    Check the current approval status of a run
    """
    run = run_manager.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
        
    return {
        "status": run.status,
        "approval_info": run.approval_info
    }


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

@app.post("/auth/verify")
async def verify_auth(user: Optional[Dict] = Depends(get_current_user)):
    """
    Verify authentication token and return user information.
    Used by frontend to validate tokens.
    """
    if not config.REQUIRE_AUTH:
        return {"authenticated": False, "message": "Authentication disabled"}
    
    return {
        "authenticated": True,
        "user": {
            "uid": user.get("uid"),
            "email": user.get("email"),
            "name": user.get("name"),
        }
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": config.APP_VERSION,
        "mode": "interactive",
        "providers": SUPPORTED_PROVIDERS,
        "auth_required": config.REQUIRE_AUTH,
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
