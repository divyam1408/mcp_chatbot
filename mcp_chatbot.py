from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from typing import List
import json
import asyncio
import aisuite as ai
import nest_asyncio

nest_asyncio.apply()

load_dotenv()


class MCP_ChatBot:
    def __init__(self):
        # Initialize session and client objects
        self.sessions = {}  # Dict mapping server name to ClientSession
        self.tool_to_server = {}  # Dict mapping tool name to server name
        self.resource_to_server = {}  # Dict mapping resource URI to server name
        self.resource_templates_to_server = {}  # Dict mapping resource template URI to server name
        self.prompt_to_server = {}  # Dict mapping prompt name to server name
        self.client = ai.Client()
        self.available_tools: List[dict] = []
        self.available_resources: List[dict] = []  # List of all resources
        self.available_resource_templates: List[
            dict
        ] = []  # List of all resource templates
        self.available_prompts: List[dict] = []  # List of all prompts
        self.model = "huggingface:Qwen/Qwen3-8B"
        self.server_config = self._load_server_config()

    def _load_server_config(self):
        """Load server configuration from servers.json"""
        try:
            with open("servers.json", "r") as f:
                config = json.load(f)
                return config.get("servers", [])
        except FileNotFoundError:
            print("Warning: servers.json not found. No servers will be connected.")
            return []
        except json.JSONDecodeError as e:
            print(f"Error parsing servers.json: {e}")
            return []

    async def process_query(self, query):
        """Process the query"""
        messages = [{"role": "user", "content": query}]

        process_query = True
        while process_query:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.available_tools
            )

            message = response.choices[0].message
            print(f"Role: {message.role}")

            if message.content:
                print(message.content)
                messages.append({"role": message.role, "content": message.content})

            if not message.tool_calls:
                process_query = False
            else:
                messages.append(
                    message
                )  # Append the assistant's message with tool calls

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_call_id = tool_call.id

                    print(f"Calling tool {tool_name} with args {tool_args}")

                    # Look up which server owns this tool
                    server_name = self.tool_to_server.get(tool_name)
                    if not server_name:
                        print(f"Error: Tool {tool_name} not found in any server")
                        continue

                    # Route the tool call to the correct server session
                    session = self.sessions.get(server_name)
                    if not session:
                        print(f"Error: Server {server_name} session not found")
                        continue

                    result = await session.call_tool(tool_name, arguments=tool_args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result.content[0].text
                            if isinstance(result.content, list)
                            else str(result.content),
                        }
                    )

    async def process_query_with_forced_tools(self, topic, num_papers=5):
        """
        Process a query by forcing the model to use tools in a specific sequence.
        First calls search_papers, then extract_info for each paper found.
        """
        print(f"\n🔍 Processing query with forced tool calls: {topic}")

        # Step 1: Force search_papers tool call
        print("\n📚 Step 1: Searching for papers...")

        # Look up which server has search_papers tool
        server_name = self.tool_to_server.get("search_papers")
        if not server_name:
            print("Error: search_papers tool not found in any server")
            return

        session = self.sessions.get(server_name)
        if not session:
            print(f"Error: Server {server_name} session not found")
            return

        search_result = await session.call_tool(
            "search_papers", arguments={"topic": topic, "max_results": num_papers}
        )

        # Extract paper IDs from the result
        # search_papers returns a list, which MCP converts to string representation
        print("SEARCH RESULT TYPE:", type(search_result))
        print("SEARCH RESULT:", search_result.structuredContent.get("result", None))
        paper_ids = search_result.structuredContent.get("result", None)
        if not paper_ids:
            print("No papers found.")
            return
        print(f"Found papers: {paper_ids}")

        # Step 2: Force extract_info for each paper
        print("\n📄 Step 2: Extracting information for each paper...")
        papers_info = []
        for paper_id in paper_ids:
            print(f"\n  Extracting info for paper: {paper_id}")

            # Look up which server has extract_info tool
            server_name = self.tool_to_server.get("extract_info")
            if not server_name:
                print("Error: extract_info tool not found in any server")
                continue

            session = self.sessions.get(server_name)
            if not session:
                print(f"Error: Server {server_name} session not found")
                continue

            extract_result = await session.call_tool(
                "extract_info", arguments={"paper_id": paper_id}
            )
            paper_info = (
                extract_result.content[0].text
                if isinstance(extract_result.content, list)
                else str(extract_result.content)
            )
            papers_info.append(json.loads(paper_info))

        # Step 3: Ask the model to summarize the results
        print("\n🤖 Step 3: Asking model to summarize the findings...")
        summary_prompt = f"""Based on the following research papers about '{topic}', please provide a brief summary:

Papers found:
{json.dumps(papers_info, indent=2)}

Please summarize the key findings and relevance of these papers."""

        messages = [{"role": "user", "content": summary_prompt}]
        response = self.client.chat.completions.create(
            model=self.model, messages=messages
        )

        message = response.choices[0].message
        if message.content:
            print(f"\n📝 Summary:\n{message.content}")

        return papers_info

    async def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Chatbot Started!")
        print("Choose mode:")
        print("  1. Optional tool calling (model decides)")
        print("  2. Forced tool calling (always uses search_papers + extract_info)")

        mode = input("\nSelect mode (1 or 2): ").strip()
        use_forced_tools = mode == "2"

        print(
            f"\n{'🔧 Forced tool mode' if use_forced_tools else '🤖 Optional tool mode'} activated!"
        )
        print("Type your queries or 'quit' to exit.")

        while True:
            try:
                query = input("\nQuery: ").strip()

                if query.lower() == "quit":
                    break

                if query.startswith("@"):
                    # Remove @ sign
                    topic = query[1:]
                    if topic == "folders":
                        resource_uri = "papers://folders"
                    else:
                        resource_uri = f"papers://{topic}"
                    await self.get_resource(resource_uri)
                    continue
                print("\n")
                if query.startswith("/"):
                    parts = query.split()
                    command = parts[0].lower()

                    if command == "/prompts":
                        await self.list_prompts()
                    elif command == "/prompt":
                        if len(parts) < 2:
                            print("Usage: /prompt <name> <arg1=value1> <arg2=value2>")
                            continue

                        prompt_name = parts[1]
                        args = {}

                        # Parse arguments
                        for arg in parts[2:]:
                            if "=" in arg:
                                key, value = arg.split("=", 1)
                                args[key] = value

                        await self.execute_prompt(prompt_name, args, use_forced_tools)
                    else:
                        print(f"Unknown command: {command}")
                    continue
                if use_forced_tools:
                    await self.process_query_with_forced_tools(query)
                else:
                    await self.process_query(query)

            except Exception as e:
                print(f"\nError: {str(e)}")

    async def get_resource(self, resource_uri):
        # 1. Try exact match in static resources
        server_name = self.resource_to_server.get(resource_uri)

        # 2. If not found, try to find a matching template
        if not server_name:
            # Simple heuristic: if the URI starts with a template prefix
            for template_uri, srv in self.resource_templates_to_server.items():
                # Check if the resource_uri matches the template (primitive match for now)
                prefix = template_uri.split("{")[0]
                if resource_uri.startswith(prefix):
                    server_name = srv
                    break

        session = self.sessions.get(server_name)

        # Fallback for papers URIs - try any research server session
        if not session and resource_uri.startswith("papers://"):
            session = self.sessions.get("research")

        if not session:
            print(f"Resource '{resource_uri}' not found or no session available.")
            return

        try:
            result = await session.read_resource(uri=resource_uri)
            if result and result.contents:
                print(f"\nResource: {resource_uri}")
                print("Content:")
                print(result.contents[0].text)
            else:
                print("No content available.")
        except Exception as e:
            print(f"Error: {e}")

    async def list_prompts(self):
        """List all available prompts."""
        if not self.available_prompts:
            print("No prompts available.")
            return

        print("\nAvailable prompts:")
        for prompt in self.available_prompts:
            print(f"- {prompt['name']}: {prompt['description']}")
            if prompt["arguments"]:
                print("  Arguments:")
                for arg in prompt["arguments"]:
                    arg_name = arg.name if hasattr(arg, "name") else arg.get("name", "")
                    print(f"    - {arg_name}")

    async def execute_prompt(self, prompt_name, args, use_forced_tools):
        """Execute a prompt with the given arguments."""
        server_name = self.prompt_to_server.get(prompt_name)
        session = self.sessions.get(server_name)
        if not session:
            print(f"Prompt '{prompt_name}' not found.")
            return
        print("ARGS:", args)
        try:
            result = await session.get_prompt(prompt_name, arguments=args)
            if result and result.messages:
                prompt_content = result.messages[0].content

                # Extract text from content (handles different formats)
                if isinstance(prompt_content, str):
                    text = prompt_content
                elif hasattr(prompt_content, "text"):
                    text = prompt_content.text
                else:
                    # Handle list of content items
                    text = " ".join(
                        item.text if hasattr(item, "text") else str(item)
                        for item in prompt_content
                    )

                print(f"\nExecuting prompt '{prompt_name}'...")
                if use_forced_tools:
                    await self.process_query_with_forced_tools(
                        args.get("topic"), args.get("num_papers")
                    )
                else:
                    await self.process_query(text)
        except Exception as e:
            print(f"Error: {e}")

    async def connect_to_servers_and_run(self):
        """Connect to all MCP servers defined in servers.json"""
        if not self.server_config:
            print("\n⚠️  No servers configured in servers.json")
            return

        print(f"\n🔌 Connecting to {len(self.server_config)} server(s)...")

        # Store all server contexts to keep them alive
        server_contexts = []

        try:
            # Connect to each server
            for server in self.server_config:
                server_name = server["name"]
                print(f"\n  Connecting to '{server_name}' server...")

                # Create server parameters
                server_params = StdioServerParameters(
                    command=server["command"],
                    args=server["args"],
                    env=server.get("env"),
                )

                # Create client context
                client_ctx = stdio_client(server_params)
                read, write = await client_ctx.__aenter__()
                server_contexts.append(client_ctx)

                # Create session context
                session_ctx = ClientSession(read, write)
                session = await session_ctx.__aenter__()
                server_contexts.append(session_ctx)

                # Initialize the session
                await session.initialize()

                # Store the session
                self.sessions[server_name] = session

                # List available tools from this server
                tools_response = await session.list_tools()
                tools = tools_response.tools

                # List available resources from this server
                try:
                    resources_response = await session.list_resources()
                    resources = resources_response.resources
                except Exception as e:
                    print(f"    ⚠️  Could not list resources: {e}")
                    resources = []

                # List available resource templates from this server
                try:
                    resource_templates_response = (
                        await session.list_resource_templates()
                    )
                    resource_templates = resource_templates_response.resourceTemplates
                except Exception as e:
                    print(f"    ⚠️  Could not list resource templates: {e}")
                    resource_templates = []

                # List available prompts from this server
                try:
                    prompts_response = await session.list_prompts()
                    prompts = prompts_response.prompts
                except Exception as e:
                    print(f"    ⚠️  Could not list prompts: {e}")
                    prompts = []

                print(
                    f"    ✓ Connected with {len(tools)} tool(s), {len(resources)} resource(s), {len(resource_templates)} template(s), {len(prompts)} prompt(s)"
                )
                print(f"      Tools: {[tool.name for tool in tools]}")
                if resources:
                    print(
                        f"      Resources: {[resource.uri for resource in resources]}"
                    )
                if resource_templates:
                    print(
                        f"      Templates: {[template.uriTemplate for template in resource_templates]}"
                    )
                if prompts:
                    print(f"      Prompts: {[prompt.name for prompt in prompts]}")

                # Build tool_to_server mapping and available_tools list
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

                # Build resource_to_server mapping and available_resources list
                for resource in resources:
                    print("RESOURCE: ", resource)
                    self.resource_to_server[str(resource.uri)] = server_name
                    self.available_resources.append(
                        {
                            "uri": str(resource.uri),
                            "name": resource.name,
                            "description": resource.description,
                            "mimeType": resource.mimeType,
                        }
                    )

                # Build resource_templates_to_server mapping and available_resource_templates list
                for template in resource_templates:
                    self.resource_templates_to_server[str(template.uriTemplate)] = (
                        server_name
                    )
                    self.available_resource_templates.append(
                        {
                            "uriTemplate": str(template.uriTemplate),
                            "name": template.name,
                            "description": template.description,
                            "mimeType": template.mimeType,
                        }
                    )

                # Build prompt_to_server mapping and available_prompts list
                for prompt in prompts:
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

            print("\n✅ All servers connected!")
            print(
                f"   Total: {len(self.available_tools)} tool(s), {len(self.available_resources)} resource(s), {len(self.available_resource_templates)} template(s), {len(self.available_prompts)} prompt(s)"
            )

            print("\n📋 Capabilities by server:")
            for server_name, session in self.sessions.items():
                print(f"\n  🔹 {server_name}:")

                # Tools
                server_tools = [
                    tool_name
                    for tool_name, srv in self.tool_to_server.items()
                    if srv == server_name
                ]
                if server_tools:
                    print(f"    Tools: {server_tools}")

                # Resources
                server_resources = [
                    uri
                    for uri, srv in self.resource_to_server.items()
                    if srv == server_name
                ]
                if server_resources:
                    print(f"    Resources: {server_resources}")

                # Resource Templates
                server_templates = [
                    uri
                    for uri, srv in self.resource_templates_to_server.items()
                    if srv == server_name
                ]
                if server_templates:
                    print(f"    Templates: {server_templates}")

                # Prompts
                server_prompts = [
                    prompt_name
                    for prompt_name, srv in self.prompt_to_server.items()
                    if srv == server_name
                ]
                if server_prompts:
                    print(f"    Prompts: {server_prompts}")

            # Run the chat loop
            await self.chat_loop()

        finally:
            # Clean up all contexts in reverse order
            for ctx in reversed(server_contexts):
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception as e:
                    print(f"Error closing context: {e}")


async def main():
    chatbot = MCP_ChatBot()
    await chatbot.connect_to_servers_and_run()


if __name__ == "__main__":
    asyncio.run(main())
