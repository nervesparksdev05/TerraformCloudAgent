"""
GitHub Service - Fetch README content from GitHub repositories.

Supports both public and private repositories via GitHub REST API.
Handles rate limiting, authentication, and error cases.
"""

import base64
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.core.logger import get_logger

logger = get_logger(__name__)


class GitHubServiceError(Exception):
    """Base exception for GitHub service errors."""
    pass


class RepositoryNotFoundError(GitHubServiceError):
    """Repository or README not found."""
    pass


class RateLimitError(GitHubServiceError):
    """GitHub API rate limit exceeded."""
    pass


class GitHubService:
    """Service for interacting with GitHub API to fetch README content."""
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    def parse_github_url(self, url: str) -> tuple[str, str]:
        """
        Parse GitHub URL to extract owner and repo name.
        
        Supports formats:
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - github.com/owner/repo
        - owner/repo
        
        Args:
            url: GitHub repository URL
            
        Returns:
            Tuple of (owner, repo)
            
        Raises:
            GitHubServiceError: If URL format is invalid
        """
        # Remove .git suffix if present
        url = url.rstrip('/').replace('.git', '')
        
        # Try to parse as full URL
        if url.startswith('http://') or url.startswith('https://'):
            parsed = urlparse(url)
            path = parsed.path.strip('/')
        elif url.startswith('github.com/'):
            path = url.replace('github.com/', '')
        else:
            # Assume it's already in owner/repo format
            path = url
        
        # Extract owner and repo
        parts = path.split('/')
        if len(parts) < 2:
            raise GitHubServiceError(
                f"Invalid GitHub URL format: {url}. Expected format: owner/repo or https://github.com/owner/repo"
            )
        
        owner, repo = parts[0], parts[1]
        
        if not owner or not repo:
            raise GitHubServiceError(f"Could not extract owner and repo from URL: {url}")
        
        logger.info(f"Parsed GitHub URL: owner={owner}, repo={repo}")
        return owner, repo
    
    async def fetch_readme(
        self, 
        repo_url: str, 
        github_token: Optional[str] = None
    ) -> dict:
        """
        Fetch README content from a GitHub repository.
        
        Args:
            repo_url: GitHub repository URL or owner/repo format
            github_token: Optional GitHub personal access token for authentication
            
        Returns:
            Dictionary containing:
            - content: Decoded README content (UTF-8)
            - filename: README filename (e.g., "README.md")
            - size: File size in bytes
            - html_url: URL to view README on GitHub
            - encoding: Content encoding (usually "base64")
            
        Raises:
            RepositoryNotFoundError: If repository or README not found
            RateLimitError: If API rate limit exceeded
            GitHubServiceError: For other API errors
        """
        try:
            owner, repo = self.parse_github_url(repo_url)
        except GitHubServiceError as e:
            logger.error(f"Failed to parse GitHub URL: {e}")
            raise
        
        # Build API URL
        api_url = f"{self.BASE_URL}/repos/{owner}/{repo}/readme"
        
        # Set up headers
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TerraformCloudAgent/1.0"
        }
        
        if github_token:
            headers["Authorization"] = f"token {github_token}"
            logger.info("Using authenticated GitHub API request")
        else:
            logger.warning("Using unauthenticated GitHub API request (rate limit: 60/hour)")
        
        try:
            logger.info(f"Fetching README from {api_url}")
            response = await self.client.get(api_url, headers=headers)
            
            # Handle rate limiting
            if response.status_code == 403:
                rate_limit_remaining = response.headers.get("X-RateLimit-Remaining", "0")
                if rate_limit_remaining == "0":
                    reset_time = response.headers.get("X-RateLimit-Reset", "unknown")
                    raise RateLimitError(
                        f"GitHub API rate limit exceeded. Resets at: {reset_time}. "
                        "Consider providing a GitHub token for higher limits (5000/hour)."
                    )
            
            # Handle not found
            if response.status_code == 404:
                raise RepositoryNotFoundError(
                    f"Repository '{owner}/{repo}' or its README not found. "
                    "Ensure the repository is public or provide a valid GitHub token."
                )
            
            # Handle other errors
            if response.status_code != 200:
                error_msg = response.json().get("message", "Unknown error")
                raise GitHubServiceError(
                    f"GitHub API error (status {response.status_code}): {error_msg}"
                )
            
            data = response.json()
            
            # Decode base64 content
            content_encoded = data.get("content", "")
            content_decoded = base64.b64decode(content_encoded).decode("utf-8")
            
            result = {
                "content": content_decoded,
                "filename": data.get("name", "README.md"),
                "size": data.get("size", 0),
                "html_url": data.get("html_url", ""),
                "encoding": data.get("encoding", "base64"),
                "download_url": data.get("download_url", "")
            }
            
            logger.info(
                f"Successfully fetched README: {result['filename']} "
                f"({result['size']} bytes)"
            )
            
            return result
            
        except httpx.RequestError as e:
            logger.error(f"Network error while fetching README: {e}")
            raise GitHubServiceError(f"Network error: {e}")
    
    async def get_rate_limit_status(self, github_token: Optional[str] = None) -> dict:
        """
        Get current GitHub API rate limit status.
        
        Args:
            github_token: Optional GitHub token
            
        Returns:
            Dictionary with rate limit information
        """
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "TerraformCloudAgent/1.0"
        }
        
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        
        try:
            response = await self.client.get(
                f"{self.BASE_URL}/rate_limit",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                core = data.get("resources", {}).get("core", {})
                return {
                    "limit": core.get("limit", 0),
                    "remaining": core.get("remaining", 0),
                    "reset": core.get("reset", 0),
                    "used": core.get("used", 0)
                }
            else:
                return {"error": "Failed to fetch rate limit status"}
                
        except httpx.RequestError as e:
            logger.error(f"Error fetching rate limit status: {e}")
            return {"error": str(e)}


# Singleton instance
_github_service: Optional[GitHubService] = None


def get_github_service() -> GitHubService:
    """Get or create the GitHub service singleton."""
    global _github_service
    if _github_service is None:
        _github_service = GitHubService()
    return _github_service
