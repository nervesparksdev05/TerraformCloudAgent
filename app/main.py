"""
FastAPI application - Main entry point
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core import config
from app.core.logger import setup_logging, get_logger
from app.models.schemas import AgentRequest, RunResponse
from app.services.llm_generator import LLMGenerator
from app.services.security_checker import SecurityChecker
from app.services.workspace_manager import WorkspaceManager
from app.services.terraform_runner import TerraformRunner

# Validate configuration on startup
# Note: config validation removed as it's now done in config.py

# Setup logging
setup_logging(
    log_dir=config.LOGS_DIR,
    log_level="DEBUG" if config.DEBUG else "INFO"
)
logger = get_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=config.APP_NAME,
    description=config.APP_DESCRIPTION,
    version=config.APP_VERSION,
    docs_url="/docs"
)

# Initialize services
workspace_manager = WorkspaceManager(base_dir=config.WORKSPACE_BASE_DIR)
llm_generator = LLMGenerator()

# Log startup
logger.info(f"Starting {config.APP_NAME} v{config.APP_VERSION}")
logger.info(f"Default Provider: {config.DEFAULT_PROVIDER.upper()}")
logger.info(f"AWS Region: {config.AWS_REGION}")
logger.info(f"GCP Project: {config.GCP_PROJECT_ID}")
logger.info(f"GCP Region: {config.GCP_REGION}")
logger.info(f"Workspace Directory: {config.WORKSPACE_BASE_DIR}")


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    logger.info("Application started successfully")
    logger.info(f"Supported providers: AWS, GCP")
    logger.info(f"Supported services: 15 per provider")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("Application shutting down")


@app.post("/runs", response_model=RunResponse)
async def create_run(request: AgentRequest):
    """
    Create and execute a Terraform run for AWS or GCP infrastructure.
    
    Supports top 15 most-used services from each provider.
    """
    run_id = None
    workspace_path = None
    
    try:
        # Step 1: Create run workspace
        logger.info(f"🚀 New deployment request: {request.request}")
        
        run_id, workspace_path = workspace_manager.create_run_workspace()
        log_path = workspace_manager.get_log_path(workspace_path)
        
        logger.info(f"📁 Workspace created: {run_id}")
        
        # Step 2: Generate Terraform using LLM
        logger.info(f"🤖 Generating {request.provider.upper()} Terraform code...")
        try:
            terraform_bundle = llm_generator.generate_terraform(
                request.request, 
                provider=request.provider
            )
            logger.info(f"✅ Terraform code generated")
        except Exception as e:
            logger.error(f"❌ LLM generation failed: {str(e)}")
            return RunResponse(
                run_id=run_id,
                status="error",
                action="apply",
                provider=request.provider,
                log_path=str(workspace_path.absolute()),
                outputs=None,
                error=str(e)
            )
        
        # Step 3: Security validation
        logger.info(f"🔒 Validating {request.provider.upper()} security...")
        is_valid, error_msg = SecurityChecker.validate(terraform_bundle, request.provider)
        if not is_valid:
            logger.error(f"❌ Security validation failed: {error_msg}")
            return RunResponse(
                run_id=run_id,
                status="error",
                action="apply",
                provider=request.provider,
                log_path=str(workspace_path.absolute()),
                outputs=None,
                error=error_msg
            )
        logger.info(f"✅ Security validation passed")
        
        # Step 4: Write files to workspace
        logger.info(f"💾 Writing files to workspace...")
        try:
            workspace_manager.write_terraform_files(workspace_path, terraform_bundle)
            workspace_manager.write_request_json(workspace_path, request)
            logger.info(f"✅ Files written")
        except Exception as e:
            logger.error(f"❌ Failed to write files: {str(e)}")
            return RunResponse(
                run_id=run_id,
                status="error",
                action="apply",
                provider=request.provider,
                log_path=str(workspace_path.absolute()),
                outputs=None,
                error=str(e)
            )
        
        # Step 5: Execute Terraform pipeline
        logger.info(f"⚙️ Executing {request.provider.upper()} Terraform pipeline...")
        
        with TerraformRunner(workspace_path, log_path) as runner:
            success, plan_summary, outputs, error = runner.run_pipeline("apply")
        
        if not success:
            logger.error(f"❌ Terraform execution failed: {error}")
            return RunResponse(
                run_id=run_id,
                status="error",
                action="apply",
                provider=request.provider,
                log_path=str(workspace_path.absolute()),
                outputs=None,
                error=error
            )
        
        # Step 6: Return success response
        logger.info(f"✅ {request.provider.upper()} deployment completed successfully!")
        if outputs:
            logger.info(f"📤 Outputs: {list(outputs.keys())}")
        
        return RunResponse(
            run_id=run_id,
            status="ok",
            action="apply",
            provider=request.provider,
            log_path=str(workspace_path.absolute()),
            outputs=outputs
        )
        
    except Exception as e:
        logger.exception(f"❌ Unexpected error: {str(e)}")
        return RunResponse(
            run_id=run_id or "unknown",
            status="error",
            action="apply",
            provider=request.provider if request else "unknown",
            log_path=str(workspace_path.absolute()) if workspace_path else "unknown",
            outputs=None,
            error=str(e)
        )


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    
    uvicorn.run(
        "app.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG
    )
