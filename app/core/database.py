"""
MongoDB Database Manager
Handles connection and operations for MongoDB
"""
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
import certifi
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

class DatabaseManager:
    _instance: Optional['DatabaseManager'] = None
    _client: Optional[MongoClient] = None
    _db: Optional[Database] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance

    def initialize(self):
        """Initialize MongoDB connection"""
        if self._client is None:
            try:
                self._client = MongoClient(
                    config.MONGODB_URI,
                    serverSelectionTimeoutMS=5000,
                    tlsCAFile=certifi.where()
                )
                # Verify connection
                self._client.admin.command('ping')
                self._db = self._client[config.MONGODB_DATABASE]
                logger.info(f"Connected to MongoDB at {config.MONGODB_URI}")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                # For development/fallback, we might want to continue optionally
                # But for this feature, it is critical.
                raise e

    @property
    def db(self) -> Database:
        if self._db is None:
            self.initialize()
        return self._db

    def get_collection(self, collection_name: str) -> Collection:
        """Get a specific collection"""
        return self.db[collection_name]

    def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            logger.info("MongoDB connection closed")

# Global instance
db_manager = DatabaseManager()
