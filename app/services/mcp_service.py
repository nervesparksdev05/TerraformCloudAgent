"""
mcp_service.py — Service for managing Model Context Protocol (MCP) server connections.

This is the single source of truth for ALL MCP operations:
  - Session management (connect, disconnect, caching)
  - Tool listing and calling
  - Schema sanitization for Gemini compatibility
  - Terraform registry context gathering (pre-generation)
  - Terraform registry validation (post-generation)
  - Gemini tool format conversion
  - MCP tool-call execution loop
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mcp import ClientSession
from mcp.client.sse import sse_client

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
    Manages connections to MCP servers via stdio transport.

    Provides both low-level operations (session management, tool calling)
    and high-level operations (registry context gathering, validation,
    Gemini tool conversion).
    """

    def __init__(self):
        self._sessions: Dict[str, ClientSession] = {}
        self._exit_stacks: Dict[str, Any] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

    # ── Session lifecycle ─────────────────────────────────────────────────────

    async def get_session(self, server_name: str, command_line: str) -> Optional[ClientSession]:
        """
        Get or create an MCP session for a given server.
        Uses AsyncExitStack to ensure all context managers are correctly exited on failure.
        """
        async with self._lock:
            if server_name in self._sessions:
                return self._sessions[server_name]

            from contextlib import AsyncExitStack
            stack = AsyncExitStack()
            try:
                # Connect to Docker service via SSE
                url = "http://mcp:8080/sse" if config.DEPLOYMENT_MODE != "development" else "http://localhost:8080/sse"

                # Enter transport context
                read, write = await stack.enter_async_context(sse_client(url))
                
                # Enter session context
                session = ClientSession(read, write)
                await stack.enter_async_context(session)
                
                # Initialize the session
                await session.initialize()
                
                self._sessions[server_name] = session
                self._exit_stacks[server_name] = stack
                
                logger.info("Initialized MCP session for server: %s", server_name)
                return session
            except Exception as e:
                logger.error("Failed to start MCP server %s: %s", server_name, e)
                # Ensure we cleanup if initialization failed
                await stack.aclose()
                return None

    async def initialize_all(self, servers: Dict[str, str]):
        """
        Pre-initialize multiple MCP servers.
        Useful for calling during application lifespan to ensure ownership by the main task.
        """
        for name, command in servers.items():
            logger.info("Pre-initializing MCP server: %s", name)
            await self.get_session(name, command)

    async def close_all(self):
        """
        Close all active MCP sessions.
        """
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
        """
        List tools available on an MCP server and update mapping (with caching).
        """
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
            return tools
        except Exception as e:
            logger.error("Failed to list tools for MCP server %s: %s", server_name, e)
            return []

    async def call_tool_by_name(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool using its name by looking up which server it belongs to.
        """
        server_name = self._tool_to_server.get(tool_name)
        if not server_name:
            raise ValueError(f"Unknown tool: {tool_name}")
            
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
        function_declarations format.

        Returns a list suitable for passing as `tools=` to Gemini's GenerativeModel.
        Returns an empty list if no tools are available.
        """
        all_mcp_tools: List[Dict[str, Any]] = []

        fetch_tasks = []
        if "terraform" in requested_servers and config.ENABLE_TERRAFORM_MCP:
            fetch_tasks.append(
                self.list_tools("terraform", config.TERRAFORM_MCP_SERVER)
            )
        if "aws" in requested_servers and config.ENABLE_AWS_MCP:
            fetch_tasks.append(
                self.list_tools("aws", config.AWS_MCP_SERVER)
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
                    "parameters": t["input_schema"],
                }
                for t in all_mcp_tools
            ]
        }]

    async def execute_tool_calls(self, tool_calls: list, timeout: float = 10.0) -> List[Dict[str, Any]]:
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

    async def gather_registry_context(self, prompt: str, session_id: str = None) -> str:
        """
        Use the Terraform MCP server + Gemini to gather registry documentation
        context before generating Terraform code.

        Opens a dedicated Docker MCP session, gives the LLM access to registry
        tools, and returns a technical summary of module versions and resource
        arguments.

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

        # Create trace for context gathering
        trace = langfuse_service.create_trace(
            name="mcp-context-gather",
            session_id=session_id,
            input=prompt
        )

        try:
            url = "http://mcp:8080/sse" if config.DEPLOYMENT_MODE != "development" else "http://localhost:8080/sse"
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
                                        parameters=sanitize_schema(t.inputSchema)
                                    )
                                ]
                            )
                        )

                    gather_system = (
                        "You are an AI context-gathering agent. Read the user's infrastructure request. "
                        "Determine if you need to look up documentation from the Terraform Registry "
                        "(like 'get_provider_details' or 'search_modules') to understand complex properties or syntaxes. "
                        "Use your tools to query the registry. Once you have enough context, reply with a focused "
                        "technical summary of the module versions and resource arguments needed to write the code. "
                        "CRITICAL: Explicitly ignore and filter out any deprecated arguments or properties from your summary. "
                        "Do NOT generate the actual `.tf` code. ONLY summarize the registry data for the coder."
                    )

                    model = genai.GenerativeModel(
                        model_name=config.GEMINI_MODEL,
                        system_instruction=gather_system,
                        tools=genai_tools
                    )
                    chat = model.start_chat()
                    response = chat.send_message(prompt)

                    # Intercept up to 5 tool calls
                    tool_call_log = []
                    for _ in range(5):
                        if not response.candidates:
                            break
                        part = response.candidates[0].content.parts[0]
                        if not getattr(part, "function_call", None):
                            break  # Native text response

                        fc = part.function_call
                        logger.info("MCP Tool called: %s", fc.name)

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
                    print(f"\n📦 MCP FINAL CONTEXT SUMMARY:\n{final_text}\n")
                    return final_text
        except Exception as e:
            logger.error("Failed async MCP gather: %s", e, exc_info=True)
            if trace:
                trace.update(level="ERROR", statusMessage=str(e))
            return ""

    def gather_registry_context_sync(self, prompt: str, session_id: str = None) -> str:
        """
        Synchronous wrapper for gather_registry_context.
        Handles the case where we may or may not be inside a running event loop.
        """
        if not config.ENABLE_TERRAFORM_MCP:
            return ""
        try:
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(asyncio.run, self.gather_registry_context(prompt, session_id))
                    return future.result(timeout=120)
            except RuntimeError: 
                # No running loop — safe to call asyncio.run() directly
                return asyncio.run(self.gather_registry_context(prompt, session_id))
        except Exception as e:
            logger.error("Failed to gather MCP context (sync): %s", e)
            return ""

    # ── Terraform registry validation (post-generation) ───────────────────────

    async def validate_terraform(self, main_tf: str) -> ValidationResult:
        """
        Post-generation validation using the Terraform MCP registry.

        Checks:
          1. Latest AWS provider version
          2. Whether each resource type exists in the registry
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
                    logger.info("validate_terraform: provider version check OK")
                except asyncio.TimeoutError:
                    logger.warning("validate_terraform: provider version check timed out")
                    notes.append("Registry: provider version check timed out.")
                except Exception as e:
                    logger.warning("validate_terraform: provider version check failed: %s", e)
                    notes.append(f"Registry: provider version check failed ({e}).")

            # ── Check 2: Verify resource types + collect registry docs ─────────
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
                                            notes.append(f"Registry: {rtype} -- docs fetched.")
                                        else:
                                            resource_docs[rtype] = raw_search[:1000]
                                            notes.append(f"Registry: {rtype} -- found in registry.")
                                    except Exception:
                                        resource_docs[rtype] = raw_search[:1000]
                                        notes.append(f"Registry: {rtype} -- found (detail fetch failed).")
                                else:
                                    resource_docs[rtype] = raw_search[:1000]
                                    notes.append(f"Registry: {rtype} -- found in registry.")
                                logger.info("validate_terraform: %s → found", rtype)
                            else:
                                notes.append(f"Registry: {rtype} -- not found (may need renaming).")
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
