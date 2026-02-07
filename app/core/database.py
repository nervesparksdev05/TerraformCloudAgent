"""
MongoDB database service for persistent state storage
"""
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, DuplicateKeyError
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

class MongoDBService:
    """MongoDB connection and operations manager"""
    
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        """Singleton pattern to reuse connection"""
        if cls._instance is None:
            cls._instance = super(MongoDBService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize MongoDB connection"""
        try:
            self._client = MongoClient(
                config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000
            )
            
            # Test connection
            self._client.admin.command('ping')
            
            self._db = self._client[config.MONGODB_DATABASE]
            
            # Create indexes
            self._create_indexes()
            
            logger.info(f"✅ MongoDB connected: {config.MONGODB_DATABASE}")
            
        except ConnectionFailure as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            logger.warning("⚠️  Falling back to file-based storage")
            self._client = None
            self._db = None
    
    def _create_indexes(self):
        """Create database indexes for performance"""
        if not self._db:
            return
            
        try:
            # Runs collection indexes
            runs = self._db.runs
            runs.create_index("run_id", unique=True)
            runs.create_index([("status", ASCENDING)])
            runs.create_index([("created_at", DESCENDING)])
            runs.create_index([("provider", ASCENDING)])
            
            # Chat messages collection indexes
            messages = self._db.chat_messages
            messages.create_index([("run_id", ASCENDING), ("timestamp", ASCENDING)])
            
            logger.debug("📊 MongoDB indexes created")
            
        except Exception as e:
            logger.warning(f"Index creation failed: {e}")
    
    @property
    def is_connected(self) -> bool:
        """Check if MongoDB is connected"""
        return self._db is not None
    
    @property
    def runs(self):
        """Get runs collection"""
        return self._db.runs if self._db else None
    
    @property
    def chat_messages(self):
        """Get chat_messages collection"""
        return self._db.chat_messages if self._db else None
    
    def insert_run(self, run_data: Dict[str, Any]) -> bool:
        """Insert a new run document"""
        if not self.is_connected:
            return False
            
        try:
            run_data["created_at"] = datetime.utcnow()
            run_data["updated_at"] = datetime.utcnow()
            self.runs.insert_one(run_data)
            logger.debug(f"💾 Saved run: {run_data.get('run_id')}")
            return True
        except DuplicateKeyError:
            logger.warning(f"Run {run_data.get('run_id')} already exists")
            return False
        except Exception as e:
            logger.error(f"Failed to insert run: {e}")
            return False
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get run by ID"""
        if not self.is_connected:
            return None
            
        try:
            run = self.runs.find_one({"run_id": run_id}, {"_id": 0})
            return run
        except Exception as e:
            logger.error(f"Failed to get run {run_id}: {e}")
            return None
    
    def update_run(self, run_id: str, update_data: Dict[str, Any]) -> bool:
        """Update run document"""
        if not self.is_connected:
            return False
            
        try:
            update_data["updated_at"] = datetime.utcnow()
            result = self.runs.update_one(
                {"run_id": run_id},
                {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update run {run_id}: {e}")
            return False
    
    def save_chat_message(self, run_id: str, role: str, content: str) -> bool:
        """Save a chat message"""
        if not self.is_connected:
            return False
            
        try:
            message = {
                "run_id": run_id,
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow()
            }
            self.chat_messages.insert_one(message)
            return True
        except Exception as e:
            logger.error(f"Failed to save chat message: {e}")
            return False
    
    def get_chat_history(self, run_id: str) -> List[Dict[str, Any]]:
        """Get chat history for a run"""
        if not self.is_connected:
            return []
            
        try:
            messages = list(self.chat_messages.find(
                {"run_id": run_id},
                {"_id": 0}
            ).sort("timestamp", ASCENDING))
            return messages
        except Exception as e:
            logger.error(f"Failed to get chat history: {e}")
            return []
    
    def list_runs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List recent runs"""
        if not self.is_connected:
            return []
            
        try:
            query = {"status": status} if status else {}
            runs = list(self.runs.find(
                query,
                {"_id": 0}
            ).sort("created_at", DESCENDING).limit(limit))
            return runs
        except Exception as e:
            logger.error(f"Failed to list runs: {e}")
            return []
    
    def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")


# Global instance
db = MongoDBService()
