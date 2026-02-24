"""
mcp_service.py — Service for managing Model Context Protocol (MCP) server connections.
"""
import asyncio
import json
import subprocess
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core import config
from app.core.logger import get_logger

logger = get_logger(__name__)

class MCPManager:
    """
    Manages connections to MCP servers via stdio transport.
    """

    def __init__(self):
        self._sessions: Dict[str, ClientSession] = {}
        self._exit_stacks: Dict[str, Any] = {}
        self._tool_to_server: Dict[str, str] = {}
        self._tools_cache: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = asyncio.Lock()

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
                # Parse command line for npx or direct executable
                parts = command_line.split()
                executable = parts[0]
                args = parts[1:]

                import os as _os
                # Inherit all env vars and explicitly ensure AWS credentials are passed to the subprocess
                _child_env = {**_os.environ}
                # Ensure AWS SDK env vars are present (from config)
                for _key in (
                    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                    "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_SESSION_TOKEN",
                ):
                    _val = _os.getenv(_key)
                    if _val:
                        _child_env[_key] = _val
                # AWS_DEFAULT_REGION fallback
                if "AWS_DEFAULT_REGION" not in _child_env and "AWS_REGION" in _child_env:
                    _child_env["AWS_DEFAULT_REGION"] = _child_env["AWS_REGION"]

                server_params = StdioServerParameters(
                    command=executable,
                    args=args,
                    env=_child_env
                )

                # Enter transport context
                read, write = await stack.enter_async_context(stdio_client(server_params))
                
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
            # Refresh tools cache if not found, maybe a new server started
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

# Singleton instance
mcp_manager = MCPManager()
