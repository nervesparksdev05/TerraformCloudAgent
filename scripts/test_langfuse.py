import os
import sys
import time
from datetime import datetime
from uuid import uuid4

# Add app to path securely
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services import langfuse_service
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

# Mock data
MOCK_SESSION_ID = f"teraf_langfuse_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
MOCK_README_CONTENT = "This is a test README. It uses Node.js and MongoDB."
MOCK_USER_MESSAGE = "I want to deploy on GCP."
MOCK_BOT_RESPONSE = "Great! Should we deploy this to dev or prod?"

MOCK_GENERATION_MESSAGES = [
    {"role": "system", "content": "You are TerraBot, a cloud deployment guide..."},
    {"role": "user", "content": MOCK_USER_MESSAGE}
]

def print_step(msg):
    print(f"\n⏳ {msg}...")

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")

def test_langfuse_integration():
    print("=" * 60)
    print(f"🚀 Starting Langfuse Integration Test")
    print(f"Session ID: {MOCK_SESSION_ID}")
    print("=" * 60)

    # Step 1: Init check
    print_step("Checking Langfuse configuration")
    if not hasattr(config, "LANGFUSE_PUBLIC_KEY") or not config.LANGFUSE_PUBLIC_KEY:
        print_error("LANGFUSE_PUBLIC_KEY not found in config")
        return
    if not hasattr(config, "LANGFUSE_SECRET_KEY") or not config.LANGFUSE_SECRET_KEY:
        print_error("LANGFUSE_SECRET_KEY not found in config")
        return
        
    client = langfuse_service.get_client()
    if not client:
        print_error("Failed to initialize Langfuse client")
        return
    
    if not langfuse_service.is_enabled():
        print_error("Langfuse tracing is disabled in langfuse_service")
        return
        
    print_success("Langfuse configured and enabled!")
    host = getattr(config, 'LANGFUSE_HOST', 'https://cloud.langfuse.com')
    print(f"   Host: {host}")

    # Step 2: README Analysis Trace
    print_step("Creating 'readme-analysis' trace")
    t0 = time.time()
    readme_trace = langfuse_service.create_trace(
        name="readme-analysis",
        session_id=MOCK_SESSION_ID,
        user_id="terraformAgent",
        input=MOCK_README_CONTENT
    )
    if readme_trace:
        time.sleep(1) # Simulate some processing
        readme_trace.update(output={"extracted_params": {"language": "Node.js", "database": "MongoDB"}, "message": "Greeting..."})
        print_success(f"Trace created: {readme_trace.id}")
    else:
        print_error("Failed to create readme-analysis trace")

    # Step 3: Conversation Turn Trace
    print_step("Creating 'conversation-turn' trace")
    conv_trace = langfuse_service.create_trace(
        name="conversation-turn",
        session_id=MOCK_SESSION_ID,
        user_id="terraformAgent",
        input="System Prompt: ...\\nUser Message: I want to deploy on GCP."
    )
    
    if conv_trace:
        # Log generation under this trace
        print_step("Logging generation span under conversation trace")
        gen_start = time.time()
        time.sleep(1) # Simulate LLM generation time
        
        gen = langfuse_service.log_generation(
            conv_trace,
            name="gemini-chat",
            model="gemini-2.5-pro",
            input_messages=MOCK_GENERATION_MESSAGES,
            output=MOCK_BOT_RESPONSE,
            start_time=gen_start,
            usage={
                "input": 120,
                "output": 45,
                "total": 165,
                "unit": "TOKENS"
            }
        )
        if gen:
            print_success(f"Generation logged: {gen.id}")
        else:
            print_error("Failed to log generation")
            
        conv_trace.update(output={"message": MOCK_BOT_RESPONSE, "is_complete": False})
        print_success(f"Conversation trace updated: {conv_trace.id}")
        
        # Log score
        print_step("Logging user feedback score")
        score = langfuse_service.log_score(
            trace_id=conv_trace.id,
            name="user-feedback",
            value=1.0,  # Thumbs up
            comment="Great helpful response!"
        )
        if score:
            print_success("Score logged successfully")
        else:
            print_error("Failed to log score")
    else:
        print_error("Failed to create conversation-turn trace")

    # Step 4: Terraform Gen Trace
    print_step("Creating 'terraform-gen' trace")
    tf_trace = langfuse_service.create_trace(
        name="terraform-gen",
        session_id=MOCK_SESSION_ID,
        input="Generate VPC and Compute Engine for GCP..."
    )
    if tf_trace:
        tf_trace.update(output={"main_tf": 'resource "google_compute_instance" "main" {}', "variables_tf": "", "outputs_tf": ""})
        print_success(f"Trace created: {tf_trace.id}")

    # Step 5: CI/CD Gen Trace
    print_step("Creating 'cicd-gen' trace")
    cicd_trace = langfuse_service.create_trace(
        name="cicd-gen",
        session_id=MOCK_SESSION_ID,
        metadata={"provider": "gcp"},
        input="Generate github actions workflow for terraform..."
    )
    if cicd_trace:
        cicd_trace.update(output="name: Terraform Pipeline\\non: [push]")
        print_success(f"Trace created: {cicd_trace.id}")

    # Step 6: Flush
    print_step("Flushing events to Langfuse")
    langfuse_service.flush()
    print_success("Flush complete!")

    print("\\n" + "=" * 60)
    print("🎉 Test Suite Completed!")
    print(f"Check your dashboard at {host}/project/.../sessions/{MOCK_SESSION_ID}")
    print("=" * 60)

if __name__ == "__main__":
    test_langfuse_integration()
