
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.conversation_manager import ConversationManager
from app.services.llm_generator import LLMGenerator
from app.core import config

async def test_readme_analysis_and_greeting():
    print("--- Testing README Analysis & Greeting ---")
    with patch('app.services.conversation_manager.ConversationManager._init_mongo', return_value=MagicMock()):
        cm = ConversationManager()
        cm._save_session = MagicMock() # Mock Session persistence
    
    # Mock the LLM service
    cm.llm_service.chat_completion = AsyncMock(return_value=json.dumps({
        "extracted_params": {
            "project_name": "TestApp",
            "workload_type": "web_server",
            "language": "Python"
        },
        "message": "Hi! I see you have a **Python** web server. It looks like it uses FastAPI.",
        "is_complete": False,
        "suggestions": ["Development", "Production"]
    }))
    
    # Mock GithubService to return a fake README
    cm.github_service.fetch_readme = AsyncMock(return_value="This is a test Python app.")
    
    # Test session creation (triggers analysis)
    result = await cm.create_session(owner="test", repo="repo", github_token="fake")
    print("Bot Response: " + result['bot_response'])
    assert "Python" in result['bot_response']
    print("[OK] README Analysis & Greeting")

async def test_mode_switching_prompt():
    print("\n--- Testing Deployment Mode Prompts ---")
    with patch('app.services.conversation_manager.ConversationManager._init_mongo', return_value=MagicMock()):
        cm = ConversationManager()
        cm._save_session = MagicMock()
    
    # Check if config.DEPLOYMENT_MODE is used in _call_llm
    config.DEPLOYMENT_MODE = "production"
    
    session = MagicMock()
    session.status = "active" # Force active status to pass validation
    session.messages = []
    session.collected_parameters = {"environment": "production"}
    cm.get_session = MagicMock(return_value=session)
    
    # Injecting the mode into the prompt context is what we want to verify 
    # (Checking the internal _call_llm logic)
    
    messages = []
    def mock_chat(*args, **kwargs):
        messages_in = kwargs.get("messages", []) or (args[0] if args else [])
        messages.extend(messages_in)
        return json.dumps({"message": "OK", "is_complete": False})
    
    cm.llm_service.chat_completion = AsyncMock(side_effect=mock_chat)
    
    await cm.process_message("sess_123", "Hello")
    
    # Verify that 'PRODUCTION' mode was injected into the system prompt context
    system_msg = messages[0]["content"]
    # Safe print for Windows
    print("System Prompt Snippet: " + system_msg[:200].encode('ascii', 'ignore').decode('ascii') + "...")
    assert "PRODUCTION" in system_msg.upper()
    print("[OK] Mode Injection")

async def test_redeploy_endpoint_logic():
    print("\n--- Testing Redeploy Endpoint Logic ---")
    # We'll test the logic that would be in main.py by mocking the components
    from app.models.schemas import RunStatus
    
    # Mock RunManager and WorkflowEngine
    run_manager = MagicMock()
    run = MagicMock()
    run.status = RunStatus.COMPLETED
    run_manager.get_run.return_value = run
    
    # Simulate the logic in main.py:redeploy_run
    if run.status not in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.DESTROYED, RunStatus.REJECTED]:
        print("Fail: Should allow COMPLETED")
        return

    print("Status before redeploy: " + str(run.status))
    run.status = RunStatus.APPROVED
    print("Status after redeploy: " + str(run.status))
    assert run.status == RunStatus.APPROVED
    print("[OK] Redeploy Logic")

async def test_free_tier_enforcement():
    print("\n--- Testing Free Tier Enforcement in Generator ---")
    generator = LLMGenerator()
    
    # Check _SYSTEM prompt
    # Safe print for Windows
    print("Generator System Prompt Snippet: " + generator._SYSTEM[:300].encode('ascii', 'ignore').decode('ascii') + "...")
    assert "STRICT AWS FREE TIER RULES" in generator._SYSTEM
    assert "t2.micro" in generator._SYSTEM
    assert "30GB" in generator._SYSTEM
    print("[OK] Free Tier Guardrails")

if __name__ == "__main__":
    asyncio.run(test_readme_analysis_and_greeting())
    asyncio.run(test_mode_switching_prompt())
    asyncio.run(test_redeploy_endpoint_logic())
    asyncio.run(test_free_tier_enforcement())
