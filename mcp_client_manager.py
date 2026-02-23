import os
import re
import json
import httpx
from typing import List, Dict, Any, Optional
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client


class MCPClientManager:
    def __init__(self, config_path: str = "servers.json"):
        self.config_path = config_path
        self.sessions: Dict[str, ClientSession] = {}
        self.tool_to_server: Dict[str, str] = {}
        self.resource_to_server: Dict[str, str] = {}
        self.resource_templates_to_server: Dict[str, str] = {}
        self.prompt_to_server: Dict[str, str] = {}

        self.available_tools: List[dict] = []
        self.available_resources: List[dict] = []
        self.available_resource_templates: List[dict] = []
        self.available_prompts: List[dict] = []

        self.server_configs: List[dict] = self._load_server_config()

    def _substitute_env_vars(self, obj: Any) -> Any:
        """Substitute environment variables in strings, lists, or dicts."""
        if isinstance(obj, str):

            def replace(match):
                return os.getenv(match.group(1), match.group(0))

            return re.sub(r"\${([^}]+)}", replace, obj)
        elif isinstance(obj, list):
            return [self._substitute_env_vars(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: self._substitute_env_vars(v) for k, v in obj.items()}
        return obj

    def _load_server_config(self) -> List[dict]:
        """Load server configuration from JSON and substitute environment variables."""
        try:
            if not os.path.exists(self.config_path):
                print(f"Warning: {self.config_path} not found.")
                return []

            with open(self.config_path, "r") as f:
                config = json.load(f)
                servers = config.get("servers", [])
                return self._substitute_env_vars(servers)
        except Exception as e:
            print(f"Error loading config {self.config_path}: {e}")
            return []

    async def connect_all(self, stack: AsyncExitStack):
        """Connect to all configured servers and initialize sessions."""
        if not self.server_configs:
            return

        print(f"\n🔌 Connecting to {len(self.server_configs)} server(s)...")

        for server in self.server_configs:
            server_name = server["name"]
            print(f"\n  Connecting to '{server_name}' server...")

            try:
                # 1. Determine transport and create client context
                transport_type = server.get("transport", "stdio")

                if transport_type == "sse":
                    url = server.get("url")
                    if not url:
                        print(f"    ⚠️ Error: 'url' required for SSE in '{server_name}'")
                        continue
                    client_ctx = sse_client(url, headers=server.get("headers"))

                elif transport_type == "http":
                    url = server.get("url")
                    if not url:
                        print(
                            f"    ⚠️ Error: 'url' required for HTTP in '{server_name}'"
                        )
                        continue
                    # Create and manage httpx client for life of this connection
                    http_client = httpx.AsyncClient(headers=server.get("headers"))
                    await stack.enter_async_context(http_client)
                    client_ctx = streamable_http_client(url, http_client=http_client)

                else:  # Default stdio
                    server_params = StdioServerParameters(
                        command=server["command"],
                        args=server["args"],
                        env=server.get("env"),
                    )
                    client_ctx = stdio_client(server_params)

                # 2. Enter client context
                result = await stack.enter_async_context(client_ctx)
                if isinstance(result, (list, tuple)) and len(result) == 3:
                    read, write, _ = result
                else:
                    read, write = result

                # 3. Create and initialize session
                session_ctx = ClientSession(read, write)
                session = await stack.enter_async_context(session_ctx)
                await session.initialize()

                self.sessions[server_name] = session

                # 4. Discover capabilities (Tools, Resources, etc.)
                await self._discover_capabilities(server_name, session)

            except Exception as e:
                print(f"    ❌ Failed to connect to '{server_name}': {e}")

        print("\n✅ All servers connected!")
        print(
            f"   Total: {len(self.available_tools)} tool(s), {len(self.available_resources)} resource(s), {len(self.available_resource_templates)} template(s), {len(self.available_prompts)} prompt(s)"
        )

    async def _discover_capabilities(self, server_name: str, session: ClientSession):
        """List and register tools, resources, templates, and prompts from a session."""

        # Tools
        tools_response = await session.list_tools()
        tools = tools_response.tools
        for tool in tools:
            self.tool_to_server[tool.name] = server_name
            self.available_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema,
                    },
                }
            )

        # Resources
        try:
            res_response = await session.list_resources()
            for res in res_response.resources:
                self.resource_to_server[str(res.uri)] = server_name
                self.available_resources.append(
                    {
                        "uri": str(res.uri),
                        "name": res.name,
                        "description": res.description,
                        "mimeType": res.mimeType,
                    }
                )
        except Exception:
            pass

        # Resource Templates
        try:
            tmpl_response = await session.list_resource_templates()
            for tmpl in tmpl_response.resourceTemplates:
                self.resource_templates_to_server[str(tmpl.uriTemplate)] = server_name
                self.available_resource_templates.append(
                    {
                        "uriTemplate": str(tmpl.uriTemplate),
                        "name": tmpl.name,
                        "description": tmpl.description,
                        "mimeType": tmpl.mimeType,
                    }
                )
        except Exception:
            pass

        # Prompts
        try:
            prompt_response = await session.list_prompts()
            for prompt in prompt_response.prompts:
                self.prompt_to_server[prompt.name] = server_name
                self.available_prompts.append(
                    {
                        "name": prompt.name,
                        "description": prompt.description,
                        "arguments": prompt.arguments
                        if hasattr(prompt, "arguments")
                        else [],
                    }
                )
        except Exception:
            pass

        print(f"    ✓ Connected: {len(tools)} tool(s)")

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Route tool call to the correct server session."""
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            raise ValueError(f"Tool {tool_name} not found in any connected server")

        session = self.sessions[server_name]
        return await session.call_tool(tool_name, arguments)

    def get_tool_schema(self, tool_name: str) -> Optional[dict]:
        """Get the input schema for a specific tool."""
        for tool in self.available_tools:
            if tool["function"]["name"] == tool_name:
                return tool["function"]["parameters"]
        return None
