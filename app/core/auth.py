"""Firebase Authentication Module

Handles Firebase token verification and user authentication for the FastAPI backend.
"""
import os
from typing import Optional, Dict
from fastapi import HTTPException, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import firebase_admin
from firebase_admin import credentials, auth
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

# Initialize Firebase Admin SDK
_firebase_app = None

def init_firebase():
    """Initialize Firebase Admin SDK with service account credentials."""
    global _firebase_app
    
    if _firebase_app is not None:
        return _firebase_app
    
    if not config.REQUIRE_AUTH:
        logger.info("Authentication disabled (REQUIRE_AUTH=false)")
        return None
    
    try:
        cred_path = config.FIREBASE_SERVICE_ACCOUNT_PATH
        if not os.path.exists(cred_path):
            raise FileNotFoundError(f"Firebase service account file not found: {cred_path}")
        
        cred = credentials.Certificate(cred_path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info(f"Firebase Admin SDK initialized for project: {config.FIREBASE_PROJECT_ID}")
        return _firebase_app
    
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        raise ValueError(f"Firebase initialization failed: {e}")


# Initialize on module load
init_firebase()

# Security scheme for Bearer tokens
security = HTTPBearer(auto_error=False)


async def verify_firebase_token(token: str) -> Dict:
    """
    Verify a Firebase ID token and return the decoded claims.
    
    Args:
        token: Firebase ID token from the client
        
    Returns:
        Dict containing user claims (uid, email, etc.)
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        decoded_token = auth.verify_id_token(token)
        logger.debug(f"Token verified for user: {decoded_token.get('email', decoded_token.get('uid'))}")
        return decoded_token
    
    except auth.InvalidIdTokenError:
        logger.warning("Invalid Firebase ID token")
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    
    except auth.ExpiredIdTokenError:
        logger.warning("Expired Firebase ID token")
        raise HTTPException(status_code=401, detail="Authentication token has expired")
    
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Optional[Dict]:
    """
    FastAPI dependency to get the current authenticated user.
    
    Returns None if authentication is disabled (REQUIRE_AUTH=false).
    Raises HTTPException if authentication is required but token is missing/invalid.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: Dict = Depends(get_current_user)):
            return {"user_id": user["uid"], "email": user["email"]}
    """
    # Skip authentication if disabled
    if not config.REQUIRE_AUTH:
        return None
    
    # Check if credentials are provided
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please provide a valid Bearer token."
        )
    
    # Verify the token
    token = credentials.credentials
    user = await verify_firebase_token(token)
    return user



