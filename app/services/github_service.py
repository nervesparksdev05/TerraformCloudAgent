
import base64
import re
from typing import Optional, Dict, Any
import httpx
from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

class GithubService:
    """
    Service to interact with GitHub API.
    """
    
    API_VERSION = "2022-11-28"
    
    def __init__(self):
        self.token = config.GITHUB_TOKEN if hasattr(config, "GITHUB_TOKEN") else None

    async def fetch_readme(self, repo_url: str, token: Optional[str] = None) -> str:
        """
        Fetch and decode the README from a public GitHub repository.
        """
        owner, repo = self._parse_repo_url(repo_url)
        if not owner or not repo:
            raise ValueError("Invalid GitHub URL. Expected format: https://github.com/owner/repo")
            
        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.API_VERSION,
            "User-Agent": "Terraform-Cloud-Agent",  # GitHub requires User-Agent
        }
        
        # Use provided token, otherwise fall back to configured token
        auth_token = token or self.token
        if auth_token:
             # Use Bearer prefix (modern standard, though 'token' still works)
             headers["Authorization"] = f"Bearer {auth_token}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                logger.debug(f"Fetching README from {api_url}")
                response = await client.get(api_url, headers=headers, follow_redirects=True)
                
                if response.status_code == 404:
                    logger.warning(f"README not found for {owner}/{repo}")
                    return ""
                    
                response.raise_for_status()
                data = response.json()
                
                # Content is Base64 encoded
                content_b64 = data.get("content", "")
                encoding = data.get("encoding", "base64")
                
                if encoding == "base64":
                    # GitHub API returns content with newlines/whitespace, strip all for clean decode
                    content_clean = "".join(content_b64.split())
                    decoded = base64.b64decode(content_clean).decode("utf-8")
                    logger.info(f"Successfully fetched README for {owner}/{repo} ({len(decoded)} chars)")
                    return decoded
                else:
                    logger.warning(f"Unexpected encoding '{encoding}' for {owner}/{repo}")
                    return content_b64

            except httpx.HTTPStatusError as e:
                logger.error(f"GitHub API HTTP {e.response.status_code} for {owner}/{repo}: {e.response.text[:200]}")
                raise ValueError(f"GitHub API returned {e.response.status_code}: {e.response.reason_phrase}")
            except base64.binascii.Error as e:
                logger.error(f"Base64 decode error for {owner}/{repo}: {e}")
                raise ValueError(f"Failed to decode README content: {e}")
            except Exception as e:
                logger.error(f"Failed to fetch README for {owner}/{repo}: {e}", exc_info=True)
                raise

    def _parse_repo_url(self, url: str) -> tuple[Optional[str], Optional[str]]:
        """
        Extract owner and repo from URL.
        """
        # Supports:
        # https://github.com/owner/repo
        # https://github.com/owner/repo.git
        # git@github.com:owner/repo.git
        pattern = r"github\.com[/:]([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)"
        match = re.search(pattern, url)
        if match:
            owner = match.group(1)
            repo = match.group(2).removesuffix(".git")  # Strip .git extension
            return owner, repo
        return None, None
