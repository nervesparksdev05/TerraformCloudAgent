import base64
from typing import Optional, List

import httpx

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


class GithubService:
    """
    Service to interact with GitHub API (owner/repo based).

    README fetching strategy:
    1) Try /repos/{owner}/{repo}/readme (GitHub decides default README)
    2) Fallback: try common README paths via /contents/{path}
    """

    API_VERSION = "2022-11-28"

    README_FALLBACK_PATHS: List[str] = [
        "README.md",
        "README.MD",
        "README",
        "readme.md",
        "docs/README.md",
        "docs/readme.md",
        "Docs/README.md",
        ".github/README.md",
    ]

    def __init__(self):
        self.token = getattr(config, "GITHUB_TOKEN", None)

    async def fetch_readme(
        self,
        owner: str,
        repo: str,
        token: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> str:
        """
        Fetch and decode README from GitHub using owner/repo.

        - Works for public or private repos (token required for private).
        - If /readme endpoint fails, tries common README locations.
        """
        owner = (owner or "").strip()
        repo = (repo or "").strip()
        if not owner or not repo:
            raise ValueError("owner and repo are required to fetch README.")

        headers = self._build_headers(token)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1) Primary endpoint
            content = await self._fetch_readme_endpoint(client, owner, repo, headers, branch)
            if content.strip():
                return content

            # 2) Fallback paths
            for path in self.README_FALLBACK_PATHS:
                content = await self._fetch_contents_path(client, owner, repo, path, headers, branch)
                if content.strip():
                    return content

        return ""

    def _build_headers(self, token: Optional[str]) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.API_VERSION,
            "User-Agent": "Terraform-Cloud-Agent",
        }
        auth_token = token or self.token
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        return headers

    @staticmethod
    def _raise_if_rate_limited(resp: httpx.Response) -> None:
        if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
            reset = resp.headers.get("X-RateLimit-Reset")
            raise ValueError(
                f"GitHub rate limit exceeded. Try later (rate resets at unix={reset}). "
                "Using a token increases limits."
            )

    @staticmethod
    def _raise_if_auth_denied(resp: httpx.Response) -> None:
        if resp.status_code in (401, 403):
            raise ValueError(
                "GitHub denied access (private repo or token missing/insufficient). "
                "Provide a GitHub token with repo access."
            )

    async def _fetch_readme_endpoint(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        headers: dict,
        branch: Optional[str],
    ) -> str:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
        params = {"ref": branch} if branch else None

        try:
            logger.debug("Fetching README via %s (ref=%s)", api_url, branch or "default")
            resp = await client.get(api_url, headers=headers, params=params, follow_redirects=True)

            self._raise_if_rate_limited(resp)
            self._raise_if_auth_denied(resp)

            if resp.status_code == 404:
                logger.warning("Default README endpoint returned 404 for %s/%s", owner, repo)
                return ""

            resp.raise_for_status()
            data = resp.json()
            return self._decode_content_blob(data, owner, repo, hint="/readme")

        except httpx.HTTPStatusError as e:
            logger.error(
                "GitHub API HTTP %s for %s/%s: %s",
                e.response.status_code, owner, repo, e.response.text[:200]
            )
            raise ValueError(f"GitHub API returned {e.response.status_code}: {e.response.reason_phrase}") from e
        except Exception as e:
            logger.error("Failed to fetch README for %s/%s: %s", owner, repo, e, exc_info=True)
            raise

    async def list_files(
        self,
        owner: str,
        repo: str,
        path: str = "",
        token: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> List[str]:
        """
        List files in a repository directory.
        """
        headers = self._build_headers(token)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": branch} if branch else None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(api_url, headers=headers, params=params, follow_redirects=True)
                self._raise_if_rate_limited(resp)
                self._raise_if_auth_denied(resp)
                
                if resp.status_code == 404:
                    return []
                
                resp.raise_for_status()
                data = resp.json()
                
                if isinstance(data, list):
                    return [item["name"] for item in data]
                return [data["name"]]
        except Exception as e:
            logger.error("Failed to list files for %s/%s at %s: %s", owner, repo, path, e)
            return []

    async def fetch_file(
        self,
        owner: str,
        repo: str,
        path: str,
        token: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> str:
        """
        Fetch a specific file's content.
        """
        headers = self._build_headers(token)
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await self._fetch_contents_path(client, owner, repo, path, headers, branch)

    async def _fetch_contents_path(
        self,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        path: str,
        headers: dict,
        branch: Optional[str],
    ) -> str:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": branch} if branch else None

        try:
            resp = await client.get(api_url, headers=headers, params=params, follow_redirects=True)

            self._raise_if_rate_limited(resp)
            self._raise_if_auth_denied(resp)

            if resp.status_code == 404:
                return ""

            resp.raise_for_status()
            data = resp.json()

            # contents endpoint can return list for directories
            if isinstance(data, list):
                return ""

            return self._decode_content_blob(data, owner, repo, hint=path)

        except httpx.HTTPStatusError:
            # treat as "not found here" and continue fallback scanning
            return ""
        except ValueError:
            # auth / rate-limit should bubble up
            raise
        except Exception as e:
            # keep quiet but log at debug so you can trace
            logger.debug("README fallback failed for %s/%s at %s: %s", owner, repo, path, e)
            return ""

    def _decode_content_blob(self, data: dict, owner: str, repo: str, hint: str) -> str:
        content_b64 = data.get("content", "") or ""
        encoding = data.get("encoding", "base64") or "base64"
        if not content_b64:
            return ""

        if encoding != "base64":
            logger.warning("Unexpected encoding '%s' for %s/%s (%s)", encoding, owner, repo, hint)
            return content_b64

        content_clean = "".join(content_b64.split())
        raw_bytes = base64.b64decode(content_clean)

        try:
            decoded = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw_bytes.decode("utf-8", errors="replace")

        logger.info("Fetched README for %s/%s via %s (%d chars)", owner, repo, hint, len(decoded))
        return decoded
