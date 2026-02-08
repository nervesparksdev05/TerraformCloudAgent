"""
MongoDB database service for persistent state storage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import ConnectionFailure, DuplicateKeyError

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


class MongoDBService:
    """MongoDB connection and operations manager."""

    _instance = None
    _client = None
    _db = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBService, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        try:
            self._client = MongoClient(
                config.MONGODB_URI,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
            )
            self._client.admin.command("ping")
            self._db = self._client[config.MONGODB_DATABASE]
            self._create_indexes()
            logger.info(f"MongoDB connected: {config.MONGODB_DATABASE}")
        except ConnectionFailure as exc:
            logger.error(f"MongoDB connection failed: {exc}")
            logger.warning("Falling back to file-based storage")
            self._client = None
            self._db = None

    def _create_indexes(self):
        if not self._db:
            return
        try:
            runs = self._db.runs
            runs.create_index("run_id", unique=True)
            runs.create_index([("status", ASCENDING)])
            runs.create_index([("created_at", DESCENDING)])
            runs.create_index([("provider", ASCENDING)])

            messages = self._db.chat_messages
            messages.create_index([("run_id", ASCENDING), ("timestamp", ASCENDING)])

            settings = self._db.settings
            settings.create_index("key", unique=True)
        except Exception as exc:
            logger.warning(f"Index creation failed: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._db is not None

    @property
    def runs(self):
        return self._db.runs if self._db else None

    @property
    def chat_messages(self):
        return self._db.chat_messages if self._db else None

    @property
    def settings(self):
        return self._db.settings if self._db else None

    def ping(self) -> bool:
        if not self._client:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:
            return False

    def insert_run(self, run_data: Dict[str, Any]) -> bool:
        if not self.is_connected:
            return False
        try:
            run_data["created_at"] = datetime.utcnow()
            run_data["updated_at"] = datetime.utcnow()
            self.runs.insert_one(run_data)
            return True
        except DuplicateKeyError:
            return False
        except Exception as exc:
            logger.error(f"Failed to insert run: {exc}")
            return False

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        try:
            return self.runs.find_one({"run_id": run_id}, {"_id": 0})
        except Exception as exc:
            logger.error(f"Failed to get run {run_id}: {exc}")
            return None

    def update_run(self, run_id: str, update_data: Dict[str, Any]) -> bool:
        if not self.is_connected:
            return False
        try:
            update_data["updated_at"] = datetime.utcnow()
            result = self.runs.update_one({"run_id": run_id}, {"$set": update_data})
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update run {run_id}: {exc}")
            return False

    def save_chat_message(self, run_id: str, role: str, content: str) -> bool:
        if not self.is_connected:
            return False
        try:
            message = {
                "run_id": run_id,
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow(),
            }
            self.chat_messages.insert_one(message)
            return True
        except Exception as exc:
            logger.error(f"Failed to save chat message: {exc}")
            return False

    def get_chat_history(self, run_id: str) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            return list(self.chat_messages.find({"run_id": run_id}, {"_id": 0}).sort("timestamp", ASCENDING))
        except Exception as exc:
            logger.error(f"Failed to get chat history: {exc}")
            return []

    def list_runs(self, limit: int = 50, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        try:
            query = {"status": status} if status else {}
            return list(self.runs.find(query, {"_id": 0}).sort("created_at", DESCENDING).limit(limit))
        except Exception as exc:
            logger.error(f"Failed to list runs: {exc}")
            return []

    def get_settings(self) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        try:
            doc = self.settings.find_one({"key": "app_settings"}, {"_id": 0, "key": 0})
            return doc
        except Exception as exc:
            logger.error(f"Failed to get settings: {exc}")
            return None

    def upsert_settings(self, payload: Dict[str, Any]) -> bool:
        if not self.is_connected:
            return False
        try:
            self.settings.update_one(
                {"key": "app_settings"},
                {"$set": {"key": "app_settings", **payload}},
                upsert=True,
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to upsert settings: {exc}")
            return False

    def delete_all_runs(self) -> Dict[str, int]:
        counts = {"runs_deleted": 0, "chat_messages_deleted": 0}
        if not self.is_connected:
            return counts
        try:
            run_result = self.runs.delete_many({})
            chat_result = self.chat_messages.delete_many({})
            counts["runs_deleted"] = int(run_result.deleted_count)
            counts["chat_messages_deleted"] = int(chat_result.deleted_count)
            return counts
        except Exception as exc:
            logger.error(f"Failed to delete all runs in MongoDB: {exc}")
            return counts

    def close(self):
        if self._client:
            self._client.close()
            logger.info("MongoDB connection closed")


db = MongoDBService()
