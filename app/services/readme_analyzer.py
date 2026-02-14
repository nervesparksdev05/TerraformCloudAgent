"""
README Analyzer - Extract deployment requirements from README using LLM.

Refactored to align with the Terraform generator prompt:
- Compact prompts (lower token usage)
- Structured output includes terraform_hints (networking + resources)
- NO fallback result: errors propagate (caller should handle HTTPException / 500)
"""

import json
from typing import Optional, Dict, Any, List

from openai import AsyncOpenAI

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


class ReadmeAnalyzer:
    """Analyze README content to extract infrastructure requirements."""

    _MAX_README_CHARS = 8000

    _SYSTEM_PROMPT = """You are a DevOps engineer. Extract deployable infrastructure requirements from a GitHub README.

Return ONLY valid JSON with these keys (always present):
{
  "provider_hint": "aws|gcp|azure|digitalocean|none",
  "environment_hint": "dev|staging|prod|unknown",
  "expected_users_hint": 0,
  "tech_stack": {"language": "python|nodejs|go|java|ruby|php|rust|other|unknown", "framework": "string", "runtime_version": "string"},
  "ports": [{"port": 0, "protocol": "tcp|udp", "purpose": "string"}],
  "dependencies": [{"type": "database|cache|queue|object_storage|search|other", "name": "string", "version": "string"}],
  "environment_variables": ["string"],
  "deployment_hints": ["string"],
  "workload_type": "web_server|api_server|background_worker|frontend|cli|other",
  "confidence": 0.0,
  "reasoning": "string",
  "terraform_hints": {
    "networking": { "mode": "create", "subnets": { "public": true, "private": false }, "nat_gateway": false },
    "resources": [
      { "type": "compute", "name": "app", "ports": [80], "count": 1 }
    ]
  }
}

Rules:
- Use ONLY what the README suggests; do not invent versions.
- If unclear, use conservative defaults and set low confidence.
- Ports must be numeric. If no port is mentioned, include one default: 8000/tcp purpose "Application".
- terraform_hints.resources MUST reflect actual dependencies inferred (omit items not needed).
- Do NOT include any load balancer hints (load balancers are not supported).
"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
        self.model = config.OPENAI_MODEL or "gpt-4"

    async def analyze(self, readme_content: str, repo_url: str) -> Dict[str, Any]:
        """
        Analyze README content to extract deployment requirements.

        NOTE: No fallback behavior. If the LLM call fails or returns invalid JSON,
        this method raises and the caller must handle it.
        """
        logger.info(f"Analyzing README for {repo_url}")

        user_prompt = self._build_user_prompt(readme_content, repo_url)

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        result_text = (response.choices[0].message.content or "").strip()
        parsed = json.loads(result_text)

        normalized = self._normalize_result(parsed)
        normalized = self._postprocess_hints(normalized)

        logger.info(
            "README analysis complete. Confidence: %.2f, Language: %s, ProviderHint: %s",
            float(normalized.get("confidence", 0.0)),
            normalized.get("tech_stack", {}).get("language", "unknown"),
            normalized.get("provider_hint", "none"),
        )
        return normalized

    def _build_user_prompt(self, readme_content: str, repo_url: str) -> str:
        content = readme_content or ""
        if len(content) > self._MAX_README_CHARS:
            content = content[: self._MAX_README_CHARS] + "\n\n[... truncated ...]"
        return f"repo={repo_url}\n\nREADME:\n{content}"

    def _normalize_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        tech_stack = data.get("tech_stack") or {}
        terraform_hints = data.get("terraform_hints") or {}

        normalized = {
            "provider_hint": (data.get("provider_hint") or "none").lower(),
            "environment_hint": (data.get("environment_hint") or "unknown").lower(),
            "expected_users_hint": int(data.get("expected_users_hint") or 0),

            "tech_stack": {
                "language": (tech_stack.get("language") or "unknown").lower(),
                "framework": tech_stack.get("framework") or "unknown",
                "runtime_version": tech_stack.get("runtime_version") or "latest",
            },
            "ports": data.get("ports") or [],
            "dependencies": data.get("dependencies") or [],
            "environment_variables": data.get("environment_variables") or [],
            "deployment_hints": data.get("deployment_hints") or [],
            "workload_type": data.get("workload_type") or "other",
            "confidence": float(data.get("confidence") or 0.0),
            "reasoning": data.get("reasoning") or "",

            "terraform_hints": {
                "networking": terraform_hints.get("networking") or {
                    "mode": "create",
                    "subnets": {"public": True, "private": False},
                    "nat_gateway": False,
                },
                "resources": terraform_hints.get("resources") or [],
            },
        }

        # Ensure ports list is usable; if empty, set default port 8000
        if not normalized["ports"]:
            normalized["ports"] = [{"port": 8000, "protocol": "tcp", "purpose": "Application"}]

        cleaned_ports = []
        for p in normalized["ports"]:
            try:
                port = int(p.get("port", 0))
            except Exception:
                port = 0
            if port <= 0:
                continue
            cleaned_ports.append({
                "port": port,
                "protocol": (p.get("protocol") or "tcp").lower(),
                "purpose": p.get("purpose") or "Application",
            })
        if not cleaned_ports:
            cleaned_ports = [{"port": 8000, "protocol": "tcp", "purpose": "Application"}]
        normalized["ports"] = cleaned_ports

        # Env vars: dedupe
        normalized["environment_variables"] = sorted(
            {str(x).strip() for x in normalized["environment_variables"] if str(x).strip()}
        )

        if normalized["provider_hint"] not in {"aws", "gcp", "azure", "digitalocean", "none"}:
            normalized["provider_hint"] = "none"

        return normalized

    def _postprocess_hints(self, data: Dict[str, Any]) -> Dict[str, Any]:
        hints = data.get("terraform_hints") or {}
        networking = hints.get("networking") or {}
        resources = hints.get("resources") or []

        # Strip any load balancer items if present
        resources = [r for r in resources if (r.get("type") or "").lower() not in {"load_balancer", "lb"}]

        # If resources empty, infer minimal deployable set from dependencies/workload
        if not resources:
            resources = self._infer_resources_from_analysis(data)

        # Ensure compute exists for server workloads
        if data.get("workload_type") in {"api_server", "web_server", "background_worker"}:
            if not any((r.get("type") or "").lower() == "compute" for r in resources):
                resources.insert(0, {"type": "compute", "name": "app", "count": 1, "ports": []})

        # Attach detected ports to compute
        ports_list = [p["port"] for p in data.get("ports", []) if isinstance(p, dict) and isinstance(p.get("port"), int)]
        for r in resources:
            if (r.get("type") or "").lower() == "compute":
                if not isinstance(r.get("ports"), list) or not r.get("ports"):
                    r["ports"] = ports_list or [8000]
                if "count" not in r or not isinstance(r.get("count"), int) or r.get("count", 0) <= 0:
                    r["count"] = 1
                r["name"] = r.get("name") or "app"

        # Networking sane defaults
        networking.setdefault("mode", "create")
        networking.setdefault("subnets", {"public": True, "private": False})
        networking.setdefault("nat_gateway", False)

        # If DB exists and is private, ensure private subnets requested
        has_private_db = any(
            (r.get("type") or "").lower() == "database" and (r.get("public") is False or str(r.get("public")).lower() == "false")
            for r in resources
        )
        if has_private_db:
            networking["subnets"] = networking.get("subnets") or {"public": True, "private": True}
            networking["subnets"]["private"] = True

        data["terraform_hints"] = {"networking": networking, "resources": resources}
        return data

    def _infer_resources_from_analysis(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        deps = data.get("dependencies") or []
        dep_text = " ".join([(d.get("name") or "") for d in deps]).lower()

        resources: List[Dict[str, Any]] = []

        # Baseline compute
        resources.append({"type": "compute", "name": "app", "count": 1, "ports": []})

        # Object storage
        if "s3" in dep_text or "bucket" in dep_text or any((d.get("type") or "") == "object_storage" for d in deps):
            resources.append({"type": "object_storage", "name": "assets"})

        # Database
        if any((d.get("type") or "") == "database" for d in deps) or any(x in dep_text for x in ["postgres", "mysql", "mariadb"]):
            engine = "postgres"
            if "mysql" in dep_text or "mariadb" in dep_text:
                engine = "mysql"
            resources.append({"type": "database", "engine": engine, "name": "appdb", "public": False})

        # NoSQL / cache
        if any((d.get("type") or "") == "cache" for d in deps) or "redis" in dep_text:
            resources.append({"type": "nosql", "name": "sessions"})
        elif any(x in dep_text for x in ["dynamodb", "cosmos", "firestore"]):
            resources.append({"type": "nosql", "name": "appdata"})

        return resources

    def get_terraform_hints(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Back-compat helper."""
        return analysis.get("terraform_hints") or {"networking": {"mode": "create"}, "resources": []}


# Singleton instance
_readme_analyzer: Optional[ReadmeAnalyzer] = None


def get_readme_analyzer() -> ReadmeAnalyzer:
    """Get or create the README analyzer singleton."""
    global _readme_analyzer
    if _readme_analyzer is None:
        _readme_analyzer = ReadmeAnalyzer()
    return _readme_analyzer
