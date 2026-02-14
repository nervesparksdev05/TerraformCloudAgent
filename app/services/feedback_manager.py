"""
Feedback Manager - Handles feedback submission and retrieval
"""
from typing import List, Optional
from datetime import datetime
import secrets

from app.core import config
from app.core.logger import get_logger
from app.models.schemas import FeedbackCreate, FeedbackResponse

logger = get_logger(__name__)

class FeedbackManager:
    def __init__(self):
        self.collection = None
        try:
            from app.core.database import db_manager
            # Ensure connection
            if db_manager._client is None:
                try:
                    db_manager.initialize()
                except Exception:
                    pass
            
            self.collection = db_manager.get_collection("feedback")
            logger.info("FeedbackManager initialized with MongoDB")
        except Exception as e:
            logger.error(f"Failed to initialize FeedbackManager: {e}")

    def submit_feedback(self, feedback: FeedbackCreate) -> FeedbackResponse:
        """Submit new feedback"""
        feedback_id = f"fb_{datetime.now():%Y%m%d}_{secrets.token_hex(4)}"
        
        feedback_entry = feedback.dict()
        feedback_entry["id"] = feedback_id
        feedback_entry["created_at"] = datetime.now()

        if self.collection is not None:
            self.collection.insert_one(feedback_entry)
        else:
            logger.warning("Feedback not persisted (MongoDB unavailable)")

        return FeedbackResponse(**feedback_entry)

    def get_all_feedback(self, limit: int = 100) -> List[FeedbackResponse]:
        """Get all feedback (admin only)"""
        if self.collection is None:
            return []

        cursor = self.collection.find().sort("created_at", -1).limit(limit)
        results = []
        for doc in cursor:
            if "_id" in doc:
                del doc["_id"]
            results.append(FeedbackResponse(**doc))
        
        return results

feedback_manager = FeedbackManager()
