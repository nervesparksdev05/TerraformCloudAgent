
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.conversation_manager import ConversationManager
from app.models.conversation_schemas import ConversationSession, ConversationStatus

# Mock config
import os
os.environ["OPENAI_API_KEY"] = "sk-test-key"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test_db"
os.environ["MONGODB_DATABASE"] = "test_db"

@pytest.fixture
def mock_db_manager():
    with patch("app.core.database.db_manager") as mock:
        mock.get_collection.return_value = MagicMock()
        yield mock

@pytest.fixture
def conversation_manager(mock_db_manager):
    return ConversationManager()

def test_create_session(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    
    # Execute
    result = conversation_manager.create_session()
    
    # Verify
    assert "session_id" in result
    session_id = result["session_id"]
    
    # Verify insert_one called
    mock_collection.insert_one.assert_called_once()
    args = mock_collection.insert_one.call_args[0][0]
    assert args["session_id"] == session_id
    assert args["provider"] == "aws"
    assert args["status"] == "active"
    assert args["run_ids"] == []

def test_get_session(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    session_id = "test_session_123"
    mock_session_data = {
        "session_id": session_id,
        "provider": "aws",
        "status": "active",
        "collected_parameters": {"test": "param"},
        "is_complete": False,
        "run_ids": [],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    mock_collection.find_one.return_value = mock_session_data
    
    # Execute
    session = conversation_manager.get_session(session_id)
    
    # Verify
    assert session is not None
    assert session.session_id == session_id
    assert session.collected_parameters == {"test": "param"}
    mock_collection.find_one.assert_called_with({"session_id": session_id})
    
def test_get_session_not_found(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    mock_collection.find_one.return_value = None
    
    # Execute
    session = conversation_manager.get_session("non_existent")
    
    # Verify
    assert session is None

def test_add_run_to_session(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    session_id = "test_session_123"
    run_id = "run_456"
    
    # Execute
    conversation_manager.add_run_to_session(session_id, run_id)
    
    # Verify
    mock_collection.update_one.assert_called_once()
    call_args = mock_collection.update_one.call_args
    query = call_args[0][0]
    update = call_args[0][1]
    
    assert query == {"session_id": session_id}
    assert update["$push"] == {"run_ids": run_id}
    assert "$set" in update
    assert "updated_at" in update["$set"]

@pytest.mark.asyncio
async def test_process_message(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    session_id = "test_session_123"
    
    # Mock existing session
    mock_session_data = {
        "session_id": session_id,
        "provider": "aws",
        "status": "active",
        "messages": [],
        "collected_parameters": {},
        "is_complete": False,
        "run_ids": [],
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    mock_collection.find_one.return_value = mock_session_data
    
    # Mock LLM call
    with patch.object(conversation_manager, "_call_llm", return_value='{"message": "Hello", "extracted_params": {"test": 1}, "is_complete": false}'):
        # Execute
        response = await conversation_manager.process_message(session_id, "Hello bot")
        
        # Verify
        assert response.bot_response == "Hello"
        assert response.collected_parameters == {"test": 1}
        
        # Verify update_one called to persist state
        mock_collection.update_one.assert_called_once()
        call_args = mock_collection.update_one.call_args
        query = call_args[0][0]
        update = call_args[0][1]
        
        assert query == {"session_id": session_id}
        assert "$set" in update
        assert len(update["$set"]["messages"]) == 2  # User + Asst
        assert update["$set"]["collected_parameters"] == {"test": 1}
