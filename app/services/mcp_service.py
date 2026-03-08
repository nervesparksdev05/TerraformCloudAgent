"""
mcp_service.py — Service for managing Model Context Protocol (MCP) server connections.

This is the single source of truth for ALL MCP operations:
  - Session management (connect, disconnect, caching) — stdio transport
  - Tool listing and calling
  - Schema sanitization for Gemini compatibility
  - Terraform Registry context gathering (pre-generation)
  - Terraform Registry validation (post-generation)
  - Gemini tool format conversion
  - MCP tool-call execution loop

Transport: stdio subprocess (terraform-mcp-server is NOT an SSE server)
Registry: registry.terraform.io — used to look up Terraform provider docs regardless of cloud.
"""
import asyncio
import json
import re
import shlex
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Result from MCP-based Terraform registry validation."""
    ok: bool = True
    notes: List[str] = field(default_factory=list)
    # Live registry data collected during validation — passed to auto-fix LLM call
    registry_context: Dict[str, Any] = field(default_factory=dict)


# ── Schema utilities ─────────────────────────────────────────────────────────

def sanitize_schema(schema: dict) -> dict:
    """
    Recursively remove unsupported validation keys from JSON schema
    for Gemini compatibility.

    Gemini only supports basic OpenAPI schema. This drops extended
    JSON schema keywords like default, minimum, maximum, etc.
    """
    drop_keys = {
        "default", "minimum", "maximum", "minLength",
        "maxLength", "pattern", "additionalProperties",
    }
    cleaned = {}
    for k, v in schema.items():
        if k in drop_keys:
            continue
        if isinstance(v, dict):
            cleaned[k] = sanitize_schema(v)
        elif isinstance(v, list) and k not in ("required", "enum"):
            cleaned[k] = [sanitize_schema(i) if isinstance(i, dict) else i for i in v]
        else:
            cleaned[k] = v
    # Gemini requires `type: object` for the root
    if schema.get("type") == "object" and "properties" not in cleaned:
        cleaned["properties"] = {}
    return cleaned


class MCPManager:
    """
    Manages connections to the Terraform MCP server via stdio transport.

    The terraform-mcp-server is a Node.js subprocess launched via npx/the installed
    binary. It connects to registry.terraform.io and exposes tools for looking up
    provider versions, resource schemas, and module documentation.

    Provides both low-level operations (session management, tool calling)
    and high-level operations (registry context gathering, validation,
    Gemini tool conversion).
    """

    def __init__(self):
        self._sessions: Dict[str, ClientSession] = {}
        self._exit_stacks: Dict[str, AsyncExitStack] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    async def get_session(self, server_name: str, command_line: str) -> Optional[ClientSession]:
        """
        Get or create an MCP session for the terraform-mcp-server subprocess.

        command_line is the executable name (e.g. "terraform-mcp-server").
        Uses stdio transport — no network server required.
        """
        async with self._lock:
            if server_name in self._sessions:
                return self._sessions[server_name]

            stack = AsyncExitStack()
            try:
                # Support multi-word commands like "docker run -i --rm hashicorp/terraform-mcp-server"
                parts = shlex.split(command_line)
                server_params = StdioServerParameters(
                    command=parts[0],
                    args=parts[1:],
                    env=None,
                )

                read, write = await stack.enter_async_context(stdio_client(server_params))
                session = ClientSession(read, write)
                await stack.enter_async_context(session)
                await session.initialize()

                self._sessions[server_name] = session
                self._exit_stacks[server_name] = stack

                logger.info("Initialized MCP session for server: %s (stdio)", server_name)
                return session
            except Exception as e:
                logger.error("Failed to start MCP server %s: %s", server_name, e)
                await stack.aclose()
                return None

    async def initialize_all(self, servers: Dict[str, str]):
        """
        Pre-initialize multiple MCP servers.
        Useful for calling during application lifespan.
        """
        for name, command in servers.items():
            logger.info("Pre-initializing MCP server: %s", name)
            await self.get_session(name, command)

    async def close_all(self):
        """Close all active MCP sessions."""
        async with self._lock:
            for server_name, stack in self._exit_stacks.items():
                try:
                    await stack.aclose()
                except RuntimeError as e:
                    # Occurs if anyio cancel scope is closed in a different task than it was entered in.
                    # We log it and move on to ensure other sessions are closed.
                    logger.warning("RuntimeError while closing MCP session stack %s: %s", server_name, e)
                except Exception as e:
                    logger.error("Error closing MCP session stack %s: %s", server_name, e)
            self._sessions.clear()
            self._exit_stacks.clear()
            self._tool_to_server.clear()
            self._tools_cache.clear()

    # ── Tool listing and calling ──────────────────────────────────────────────

    async def list_tools(self, server_name: str, command_line: str) -> List[Dict[str, Any]]:
        """List tools available on an MCP server and update mapping (with caching)."""
        if server_name in self._tools_cache:
            return self._tools_cache[server_name]

        session = await self.get_session(server_name, command_line)
        if not session:
            return []

        try:
            tools_result = await session.list_tools()
            tools = []
            for tool in tools_result.tools:
                tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema
                })
                self._tool_to_server[tool.name] = server_name

            self._tools_cache[server_name] = tools
            logger.info("Listed %d tools from MCP server '%s'", len(tools), server_name)
            return tools
        except Exception as e:
            logger.error("Failed to list tools for MCP server %s: %s", server_name, e)
            return []

    async def call_tool_by_name(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool using its name by looking up which server it belongs to."""
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            raise ValueError(f"Unknown tool: {tool_name}. Have you called list_tools first?")

        session = self._sessions.get(server_name)
        if not session:
            raise RuntimeError(f"No active session for MCP server: {server_name}")

        try:
            logger.info("Calling MCP tool: %s:%s with args: %s", server_name, tool_name, arguments)
            result = await session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logger.error("Failed to call tool %s on MCP server %s: %s", tool_name, server_name, e)
            raise

    # ── Gemini tool format conversion ─────────────────────────────────────────

    async def get_gemini_tools(self, requested_servers: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch tools from requested MCP servers and convert them to Gemini
        function_declarations format, with schema sanitization.

        Returns a list suitable for passing as `tools=` to Gemini's GenerativeModel.
        Returns an empty list if no tools are available.
        """
        all_mcp_tools: List[Dict[str, Any]] = []

        fetch_tasks = []
        if "terraform" in requested_servers and config.ENABLE_TERRAFORM_MCP:
            fetch_tasks.append(
                self.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
            )

        if fetch_tasks:
            results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list):
                    all_mcp_tools.extend(res)
                else:
                    logger.error("Error fetching MCP tools: %s", res)

        if not all_mcp_tools:
            return []

        return [{
            "function_declarations": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": sanitize_schema(t["input_schema"]) if isinstance(t["input_schema"], dict) else t["input_schema"],
                }
                for t in all_mcp_tools
            ]
        }]

    async def execute_tool_calls(self, tool_calls: list, timeout: float = 30.0) -> List[Dict[str, Any]]:
        """
        Execute a batch of MCP tool calls from a Gemini function_call response.

        Args:
            tool_calls: list of Gemini function_call objects (each has .name and .args)
            timeout: per-tool timeout in seconds

        Returns:
            list of function_response dicts ready to send back to Gemini
        """
        tool_responses = []

        for tc in tool_calls:
            try:
                mcp_res = await asyncio.wait_for(
                    self.call_tool_by_name(tc.name, tc.args),
                    timeout=timeout,
                )
                tool_responses.append({
                    "function_response": {
                        "name": tc.name,
                        "response": {"result": str(mcp_res.content)},
                    }
                })
            except asyncio.TimeoutError:
                tool_responses.append({
                    "function_response": {
                        "name": tc.name,
                        "response": {"error": f"Tool timed out after {timeout}s"},
                    }
                })
            except Exception as e:
                tool_responses.append({
                    "function_response": {
                        "name": tc.name,
                        "response": {"error": str(e)},
                    }
                })

        return tool_responses

    # ── Registry context gathering (pre-generation) ───────────────────────────

    async def gather_registry_context(
        self, 
        prompt: str, 
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> str:
        """
        Use the Terraform Registry MCP server + Gemini to gather live provider
        documentation before generating Terraform code.

        Opens a dedicated MCP session (stdio subprocess), gives the LLM access to
        registry tools (get_provider_details, search_modules, get_latest_provider_version,
        etc.), and returns a focused technical summary of provider versions and resource
        argument schemas needed for the Terraform code.

        This is provider-agnostic at the MCP level — the LLM decides which provider
        to look up based on the prompt. For AWS Terraform, it will naturally query
        hashicorp/aws.

        Returns empty string if MCP is disabled or gathering fails.
        """
        if not config.ENABLE_TERRAFORM_MCP:
            return ""

        try:
            import google.generativeai as genai
            from google.generativeai.types import Tool, FunctionDeclaration
        except ImportError as e:
            logger.warning("google.generativeai not available for MCP context gathering: %s", e)
            return ""

        from app.services import langfuse_service

        # Use passed identity or fall back to session-based identity if available
        _user_id = user_id
        _username = username
        
        if not _user_id and session_id:
            # Fallback to session-based identity for legacy/anonymous calls
            # Use the session_id as the user_id for grouping
            _user_id = session_id
            _username = f"anon-{session_id[:8]}"

        # Create trace for context gathering
        trace = langfuse_service.create_trace(
            name="mcp-context-gather",
            session_id=session_id,
            user_id=_user_id,
            username=_username,
            input=prompt,
        )

        try:
            url = config.MCP_SSE_URL
            logger.info("gather_registry_context: connecting to MCP SSE at %s", url)
            async with sse_client(url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools_response = await session.list_tools()

                    genai_tools = []
                    for t in tools_response.tools:
                        genai_tools.append(
                            Tool(
                                function_declarations=[
                                    FunctionDeclaration(
                                        name=t.name,
                                        description=t.description,
                                        parameters=sanitize_schema(t.inputSchema) if isinstance(t.inputSchema, dict) else None
                                    )
                                ]
                            )
                        )

                    gather_system = (
                        "You are a Terraform Registry context-gathering agent. "
                        "Read the user's infrastructure request carefully. "
                        "Use the Terraform Registry tools (such as 'get_provider_details', "
                        "'search_providers', 'get_latest_provider_version', 'search_modules') "
                        "to look up current documentation for the providers and resources needed. "
                        "Focus on the providers and resource types mentioned in the request. "
                        "Once you have gathered enough context, reply with a concise technical "
                        "summary covering: (1) the latest provider version constraint to use, "
                        "(2) correct argument names for the resource types needed, "
                        "(3) any deprecated arguments to avoid. "
                        "CRITICAL: Filter out deprecated arguments. "
                        "Do NOT generate actual .tf code. Only summarize registry data."
                    )

                    model = genai.GenerativeModel(
                        model_name=config.GEMINI_MODEL,
                        system_instruction=gather_system,
                        tools=genai_tools
                    )
                    chat = model.start_chat()
                    response = chat.send_message(prompt)

                    # Intercept up to 8 tool calls
                    tool_call_log = []
                    for _ in range(8):
                        if not response.candidates:
                            break
                        part = response.candidates[0].content.parts[0]
                        if not getattr(part, "function_call", None):
                            break  # Native text response — done

                        fc = part.function_call
                        logger.info("MCP Registry Tool called: %s", fc.name)

                        args = {k: v for k, v in fc.args.items()} if hasattr(fc.args, "items") else dict(fc.args)
                        try:
                            mcp_result = await session.call_tool(fc.name, arguments=args)
                            result_text = "\\n".join(c.text for c in mcp_result.content if c.type == "text")
                            print(f"\n🔧 MCP TOOL RESULT — {fc.name}")
                            print(f"   Args: {args}")
                            print(f"   Result:\n{result_text[:3000]}\n")
                        except Exception as e:
                            logger.error("MCP Tool '%s' failed: %s", fc.name, e)
                            result_text = f"Error: {e}"

                        # Log each tool call as a Langfuse span
                        tool_call_entry = {
                            "tool": fc.name,
                            "args": args,
                            "result_preview": result_text[:2000],
                        }
                        tool_call_log.append(tool_call_entry)

                        if trace:
                            try:
                                trace.span(
                                    name=f"mcp-tool:{fc.name}",
                                    input=args,
                                    output=result_text[:5000],
                                )
                            except Exception:
                                pass

                        # Feed the tool response back into Gemini
                        response = chat.send_message(
                            {"function_response": {"name": fc.name, "response": {"result": result_text[:10000]}}}
                        )

                    final_text = response.text if hasattr(response, "text") else getattr(
                        response.candidates[0].content.parts[0], "text", "No context gathered."
                    )
                    if trace:
                        langfuse_service.log_generation(
                            trace,
                            name="gemini-mcp-gather",
                            model=config.GEMINI_MODEL,
                            input_messages=[{"role": "user", "content": prompt}],
                            output=final_text
                        )
                        try:
                            trace.update(output={
                                "context_summary": final_text[:5000],
                                "tool_calls": tool_call_log,
                            })
                        except Exception:
                            pass
                    return final_text
        except Exception as e:
            logger.error("Failed async MCP gather: %s", e, exc_info=True)
            if trace:
                try:
                    trace.update(level="ERROR", statusMessage=str(e))
                except Exception:
                    pass
            return ""

    def gather_registry_context_sync(
        self, 
        prompt: str, 
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> str:
        """
        Synchronous wrapper for gather_registry_context.
        Handles the case where we may or may not be inside a running event loop.
        """
        if not config.ENABLE_TERRAFORM_MCP:
            return ""
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return asyncio.run_coroutine_threadsafe(
                        self.gather_registry_context(prompt, session_id, user_id, username), loop
                    ).result()
                else:
                    return loop.run_until_complete(
                        self.gather_registry_context(prompt, session_id, user_id, username)
                    )
            except RuntimeError:
                # No running loop, run a new one
                return asyncio.run(self.gather_registry_context(prompt, session_id, user_id, username))
        except Exception as e:
            logger.error("Failed to gather MCP registry context (sync): %s", e)
            return ""

    # ── Terraform registry validation (post-generation) ───────────────────────

    async def validate_terraform(
        self,
        main_tf: str,
        session_id: str = None,
        user_id: str = None,
        username: str = None,
    ) -> ValidationResult:
        """
        Post-generation validation using the Terraform Registry MCP server.

        Checks:
          1. Latest AWS provider version via get_latest_provider_version
          2. Whether each aws_* resource type exists in the registry
          3. Collects registry documentation for auto-fix

        Returns a ValidationResult with notes and registry_context.
        """
        if not config.ENABLE_TERRAFORM_MCP:
            logger.debug("validate_terraform: ENABLE_TERRAFORM_MCP=False — skipping.")
            return ValidationResult(ok=True, notes=["MCP validation skipped (disabled)."])

        from app.services import langfuse_service

        # Extract resource types for the trace input
        resource_types_found = re.findall(r'resource\s+"(aws_[\w]+)"', main_tf) if main_tf else []

        trace = langfuse_service.create_trace(
            name="MCP Validation",
            session_id=session_id,
            user_id=user_id,
            username=username,
            input={"resource_types": list(set(resource_types_found))[:8],
                   "main_tf_length": len(main_tf or "")},
        )

        notes: List[str] = []
        ok = True
        registry_context: Dict[str, Any] = {}

        try:
            tools = await self.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
            if not tools:
                logger.warning("validate_terraform: No MCP tools available — skipping registry check.")
                return ValidationResult(ok=True, notes=["MCP validation skipped (no tools available)."])

            tool_names = {t["name"] for t in tools}
            logger.info("validate_terraform: %d MCP tools available", len(tools))

            # ── Check 1: Latest provider version ──────────────────────────────
            if "get_latest_provider_version" in tool_names:
                try:
                    result = await asyncio.wait_for(
                        self.call_tool_by_name(
                            "get_latest_provider_version",
                            {"namespace": "hashicorp", "name": "aws"},
                        ),
                        timeout=15.0,
                    )
                    version_info = str(result.content) if result else ""
                    registry_context["aws_provider_version"] = version_info
                    notes.append(f"Registry: hashicorp/aws provider — {version_info[:120]}")
                    logger.info("validate_terraform: AWS provider version check OK")
                except asyncio.TimeoutError:
                    logger.warning("validate_terraform: provider version check timed out")
                    notes.append("Registry: AWS provider version check timed out.")
                except Exception as e:
                    logger.warning("validate_terraform: provider version check failed: %s", e)
                    notes.append(f"Registry: AWS provider version check failed ({e}).")

            # ── Check 2: Verify aws_* resource types + collect registry docs ──
            if main_tf:
                resource_types = list(set(re.findall(r'resource\s+"(aws_[\w]+)"', main_tf)))
                resource_docs: Dict[str, str] = {}

                for rtype in resource_types[:8]:
                    if "search_providers" in tool_names:
                        try:
                            search_result = await asyncio.wait_for(
                                self.call_tool_by_name(
                                    "search_providers",
                                    {
                                        "provider_name": "aws",
                                        "provider_namespace": "hashicorp",
                                        "service_slug": rtype,
                                        "provider_document_type": "resources",
                                    },
                                ),
                                timeout=15.0,
                            )
                            if search_result and search_result.content:
                                raw_search = str(search_result.content)
                                doc_id_match = re.search(r'"provider_doc_id"\s*:\s*"?(\d+)"?', raw_search)
                                if doc_id_match and "get_provider_details" in tool_names:
                                    doc_id = doc_id_match.group(1)
                                    try:
                                        detail_result = await asyncio.wait_for(
                                            self.call_tool_by_name(
                                                "get_provider_details",
                                                {"provider_doc_id": doc_id},
                                            ),
                                            timeout=15.0,
                                        )
                                        if detail_result and detail_result.content:
                                            resource_docs[rtype] = str(detail_result.content)[:3000]
                                            notes.append(f"Registry: {rtype} — docs fetched.")
                                        else:
                                            resource_docs[rtype] = raw_search[:1000]
                                            notes.append(f"Registry: {rtype} — found in registry.")
                                    except Exception:
                                        resource_docs[rtype] = raw_search[:1000]
                                        notes.append(f"Registry: {rtype} — found (detail fetch failed).")
                                else:
                                    resource_docs[rtype] = raw_search[:1000]
                                    notes.append(f"Registry: {rtype} — found in registry.")
                                logger.info("validate_terraform: %s → found", rtype)
                            else:
                                notes.append(f"Registry: {rtype} — not found (may need renaming).")
                                ok = False
                                logger.warning("validate_terraform: %s → NOT FOUND", rtype)
                        except asyncio.TimeoutError:
                            logger.warning("validate_terraform: search timed out for %s", rtype)
                            notes.append(f"Registry: {rtype} — check timed out.")
                        except Exception as e:
                            logger.warning("validate_terraform: search failed for %s: %s", rtype, e)
                            notes.append(f"Registry: {rtype} — search error ({e}).")

                if resource_docs:
                    registry_context["resource_docs"] = resource_docs

        except Exception as e:
            logger.error("validate_terraform: unexpected error: %s", e, exc_info=True)
            notes.append(f"MCP validation error: {e}")
            ok = True  # Non-blocking

        validation_result = ValidationResult(ok=ok, notes=notes, registry_context=registry_context)
        print(f"\n✅ MCP VALIDATION RESULT:")
        print(f"   OK: {ok}")
        print(f"   Notes: {notes}")
        print(f"   Registry docs fetched for: {list(registry_context.get('resource_docs', {}).keys())}\n")

        # Record validation outcome on the trace
        if trace:
            try:
                trace.update(output={
                    "ok": ok,
                    "notes": notes,
                    "resources_checked": len(resource_types_found),
                    "has_registry_context": bool(registry_context),
                })
            except Exception:
                pass

        return validation_result


# Singleton instance
mcp_manager = MCPManager()
