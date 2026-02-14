
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from app.services.conversation_manager import ConversationManager

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

def test_list_sessions(conversation_manager, mock_db_manager):
    # Setup
    mock_collection = mock_db_manager.get_collection.return_value
    
    # Mock data
    now = datetime.now()
    mock_docs = [
        {
            "session_id": "sess_1",
            "messages": [{"role": "user", "content": "I want a web server"}],
            "updated_at": now,
            "created_at": now
        },
        {
            "session_id": "sess_2",
            "messages": [{"role": "user", "content": "Deploy DB"}],
            "updated_at": now - timedelta(hours=1),
            "created_at": now - timedelta(hours=1)
        }
    ]
    
    # Mock cursor chain: find -> sort -> limit -> iter
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value = mock_cursor
    mock_cursor.limit.return_value = mock_cursor
    mock_cursor.__iter__.return_value = iter(mock_docs)
    
    mock_collection.find.return_value = mock_cursor
    
    # Execute
    sessions = conversation_manager.list_sessions(limit=10)
    
    # Verify
    assert len(sessions) == 2
    expected_date = now.strftime("%b %d")
    assert sessions[0]["session_id"] == "sess_1"
    assert sessions[0]["title"] == f"I want a web server - {expected_date}"
    assert sessions[1]["session_id"] == "sess_2"
    assert sessions[1]["title"] == f"Deploy DB - {expected_date}"
    
    # Verify DB call
    mock_collection.find.assert_called_once()
    mock_cursor.sort.assert_called_with("updated_at", -1)
    mock_cursor.limit.assert_called_with(10)
