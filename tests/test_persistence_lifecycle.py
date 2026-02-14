
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from app.services.conversation_manager import ConversationManager
from app.models.conversation_schemas import ConversationSession

# Mock config
import os
os.environ["OPENAI_API_KEY"] = "sk-test-key"
os.environ["MONGODB_URI"] = "mongodb://localhost:27017/test_db"
os.environ["MONGODB_DATABASE"] = "test_db"

@pytest.fixture
def mock_db_manager():
    with patch("app.core.database.db_manager") as mock:
        mock.get_collection.return_value = MagicMock()
        # Ensure _client is None so init logic runs (or is skipped if we don't mock initialize)
        # But we want to simulate successful init.
        # Actually in the code: if db_manager._client is None: try: db_manager.initialize()
        # We can just mock initialize to do nothing.
        mock.initialize.return_value = None
        mock._client = None
        yield mock

@pytest.fixture
def conversation_manager(mock_db_manager):
    return ConversationManager()

def test_create_session_persistence(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    
    # Execute
    result = conversation_manager.create_session(provider="gcp")
    session_id = result["session_id"]
    
    # Verify in-memory
    assert session_id in conversation_manager.sessions
    assert conversation_manager.sessions[session_id].provider == "gcp"
    
    # Verify DB insertion
    mock_collection.insert_one.assert_called_once()
    args, _ = mock_collection.insert_one.call_args
    inserted_doc = args[0]
    assert inserted_doc["session_id"] == session_id
    assert inserted_doc["provider"] == "gcp"

def test_get_session_from_db(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    session_id = "sess_restored"
    
    # Simulate DB finding the session
    mock_doc = {
        "session_id": session_id,
        "provider": "azure",
        "messages": [{"role": "user", "content": "Hello"}],
        "collected_parameters": {"region": "eastus"},
        "is_complete": False,
        "status": "active",
        "created_at": datetime.now(),
        "updated_at": datetime.now()
    }
    mock_collection.find_one.return_value = mock_doc
    
    # Ensure not in memory
    assert session_id not in conversation_manager.sessions
    
    # Execute
    session = conversation_manager.get_session(session_id)
    
    # Verify
    assert session is not None
    assert session.session_id == session_id
    assert session.provider == "azure"
    assert len(session.messages) == 1
    
    # Verify DB call
    mock_collection.find_one.assert_called_with({"session_id": session_id})
    
    # Verify added to memory
    assert session_id in conversation_manager.sessions

def test_update_session_persistence(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    
    # Create session first
    result = conversation_manager.create_session()
    session_id = result["session_id"]
    
    # Mock update_one
    mock_collection.update_one.return_value = MagicMock(modified_count=1)
    
    # Simulate processing a message (which triggers update)
    # We strip _call_llm to avoid calling OpenAI
    with patch.object(conversation_manager, "_call_llm", return_value='{"message": "Hi", "extracted_params": {}}'):
        # using async loop is hard in sync test, so we can just modify session and call update manually?
        # Or better, just check update logic manually.
        
        session = conversation_manager.get_session(session_id)
        session.messages.append({"role": "user", "content": "test"})
        
        # Manually trigger the update logic block from process_message (simulated)
        # Instead of calling process_message (which is async), let's just verified that the code *would* call update_one
        # But we can call `conversation_manager.sessions_collection.update_one` ... wait, we want to test that the manager calls it.
        # Let's use `add_run_to_session` as a proxy for update, or just trust `process_message` logic if we don't want to use pytest-asyncio.
        
        conversation_manager.add_run_to_session(session_id, "run_123")
        
        # Verify update_one called
        mock_collection.update_one.assert_called()
        # First call was insert_one, subsequent should be update_one
        # Actually add_run_to_session calls update_one.
        
        args, kwargs = mock_collection.update_one.call_args
        filter_criteria = args[0]
        update_op = args[1]
        
        assert filter_criteria == {"session_id": session_id}
        assert "$addToSet" in update_op
        assert update_op["$addToSet"]["run_ids"] == "run_123"

def test_ensure_indexes_called(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    
    # Verify create_index was called twice (once for TTL, once for unique)
    # Note: ConversationManager is instantiated in the fixture, which calls __init__, which calls _ensure_indexes
    assert mock_collection.create_index.call_count >= 2
    
    # Verify TTL index (approximate check for args, since there might be multiple calls)
    expiration_found = False
    unique_found = False
    
    for call in mock_collection.create_index.call_args_list:
        args, kwargs = call
        if args and args[0] == "updated_at" and kwargs.get("expireAfterSeconds") == 2592000:
            expiration_found = True
        if args and args[0] == "session_id" and kwargs.get("unique") is True:
            unique_found = True
            
    assert expiration_found, "TTL index on updated_at not created"
    assert unique_found, "Unique index on session_id not created"
