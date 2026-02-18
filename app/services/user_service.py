"""
User Service - MongoDB user management
Syncs Firebase-authenticated users into MongoDB on every login.
"""
from datetime import datetime, timezone
from typing import Optional, Dict
from pymongo import ReturnDocument
from app.core.database import db_manager
from app.core.logger import get_logger

logger = get_logger(__name__)

USERS_COLLECTION = "users"


class UserService:
    """Handles upsert and retrieval of users in MongoDB."""

    @property
    def collection(self):
        return db_manager.get_collection(USERS_COLLECTION)

    def upsert_user(self, firebase_user: Dict) -> Dict:
        """
        Upsert a user record from a verified Firebase token payload.

        Args:
            firebase_user: Decoded Firebase token dict containing uid, email, etc.

        Returns:
            The MongoDB user document (without _id).
        """
        uid = firebase_user.get("uid") or firebase_user.get("user_id")
        email = firebase_user.get("email", "")
        name = firebase_user.get("name", "")
        picture = firebase_user.get("picture", "")
        provider = self._detect_provider(firebase_user)
        now = datetime.now(timezone.utc)

        update_doc = {
            "$set": {
                "uid": uid,
                "email": email,
                "display_name": name,
                "photo_url": picture,
                "provider": provider,
                "last_login": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "created_at": now,
            }
        }

        result = self.collection.find_one_and_update(
            {"uid": uid},
            update_doc,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

        # Convert ObjectId to string for JSON serialisation
        if result and "_id" in result:
            result["_id"] = str(result["_id"])

        logger.info(f"User upserted: uid={uid}, email={email}, provider={provider}")
        return result

    def get_user_by_uid(self, uid: str) -> Optional[Dict]:
        """Retrieve a user document by Firebase UID."""
        doc = self.collection.find_one({"uid": uid})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Retrieve a user document by email address."""
        doc = self.collection.find_one({"email": email})
        if doc and "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc

    def _detect_provider(self, firebase_user: Dict) -> str:
        """Detect sign-in provider from Firebase token claims."""
        identities = firebase_user.get("firebase", {}).get("identities", {})
        if "google.com" in identities:
            return "google"
        sign_in_provider = firebase_user.get("firebase", {}).get("sign_in_provider", "")
        if sign_in_provider == "google.com":
            return "google"
        return "email"


# Singleton instance
user_service = UserService()
