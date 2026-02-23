import json
import asyncio
from contextlib import AsyncExitStack
from dotenv import load_dotenv
import aisuite as ai
import nest_asyncio
from mcp_client_manager import MCPClientManager

nest_asyncio.apply()
load_dotenv()


class MCP_ChatBot:
    def __init__(self):
        self.mcp_manager = MCPClientManager()
        self.client = ai.Client()
        self.model = "huggingface:Qwen/Qwen3-8B"

    async def _call_mcp_tool(self, tool_name: str, tool_args: dict) -> str:
        """Helper to call MCP tool and format result."""
        try:
            result = await self.mcp_manager.call_tool(tool_name, tool_args)
            return (
                result.content[0].text
                if isinstance(result.content, list)
                else str(result.content)
            )
        except Exception as e:
            return f"Error calling tool: {e}"

    async def process_query(self, query):
        """Process the query"""
        system_prompt = """You are an expert research assistant capable of using tools at your exposure and return
        relevent information given a query.
        Use the relevent available tools to answer the user query"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        process_query = True
        while process_query:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.mcp_manager.available_tools,
            )

            message = response.choices[0].message
            print(f"Role: {message.role}")

            if message.content:
                print(message.content)
                messages.append({"role": message.role, "content": message.content})

            if not message.tool_calls:
                process_query = False
            else:
                messages.append(message)

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)
                    tool_call_id = tool_call.id

                    print(f"Calling tool {tool_name} with args {tool_args}")
                    result_text = await self._call_mcp_tool(tool_name, tool_args)

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": result_text,
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

        try:
            search_result = await self.mcp_manager.call_tool(
                "search_papers", arguments={"topic": topic, "max_results": num_papers}
            )
            paper_ids = search_result.structuredContent.get("result", None)
        except Exception as e:
            print(f"Error searching papers: {e}")
            return

        if not paper_ids:
            print("No papers found.")
            return
        print(f"Found papers: {paper_ids}")

        # Step 2: Force extract_info for each paper
        print("\n📄 Step 2: Extracting information for each paper...")
        papers_info = []
        for paper_id in paper_ids:
            print(f"\n  Extracting info for paper: {paper_id}")
            try:
                extract_result = await self.mcp_manager.call_tool(
                    "extract_info", arguments={"paper_id": paper_id}
                )
                paper_info_json = (
                    extract_result.content[0].text
                    if isinstance(extract_result.content, list)
                    else str(extract_result.content)
                )
                papers_info.append(json.loads(paper_info_json))
            except Exception as e:
                print(f"Error extracting info for {paper_id}: {e}")

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
                    # Remove @ sign and split
                    cmd_line = query[1:].strip()
                    if not cmd_line:
                        continue

                    parts = cmd_line.split()
                    cmd_or_tool = parts[0]
                    args_raw = parts[1:]

                    # Support '@git list_commits ...' style by shifting
                    if cmd_or_tool == "git" and len(parts) > 1:
                        cmd_or_tool = parts[1]
                        args_raw = parts[2:]

                    # 1. Try to find if it's a tool
                    schema = self.mcp_manager.get_tool_schema(cmd_or_tool)
                    if schema:
                        args = {}
                        properties = schema.get("properties", {})
                        # Sort properties to have a stable positional mapping if 'required' is not enough
                        prop_names = list(properties.keys())
                        required_props = schema.get("required", [])

                        # Use required props order first, then remaining props
                        mapping_order = required_props + [
                            p for p in prop_names if p not in required_props
                        ]

                        for i, arg in enumerate(args_raw):
                            if "=" in arg:
                                k, v = arg.split("=", 1)
                                args[k] = v
                            elif i < len(mapping_order):
                                args[mapping_order[i]] = arg

                        print(f"🔧 Executing @{cmd_or_tool} with {args}")
                        result_text = await self._call_mcp_tool(cmd_or_tool, args)
                        print(f"\n{result_text}")
                        continue

                    # 2. Try to handle as a resource (ArXiv papers or templates)
                    if cmd_or_tool == "folders":
                        resource_uri = "papers://folders"
                    else:
                        resource_uri = f"papers://{cmd_line}"

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
        """Read an MCP resource."""
        # Seek server through manager
        server_name = self.mcp_manager.resource_to_server.get(resource_uri)

        if not server_name:
            # Try matching template
            for (
                template_uri,
                srv,
            ) in self.mcp_manager.resource_templates_to_server.items():
                prefix = template_uri.split("{")[0]
                if resource_uri.startswith(prefix):
                    server_name = srv
                    break

        if not server_name:
            print(f"Resource '{resource_uri}' not found.")
            return

        session = self.mcp_manager.sessions.get(server_name)
        if not session:
            print(f"No session for server '{server_name}'")
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
            print(f"Error reading resource: {e}")

    async def list_prompts(self):
        """List all available prompts."""
        prompts = self.mcp_manager.available_prompts
        if not prompts:
            print("No prompts available.")
            return

        print("\nAvailable prompts:")
        for prompt in prompts:
            print(f"- {prompt['name']}: {prompt['description']}")
            if prompt["arguments"]:
                print("  Arguments:")
                for arg in prompt["arguments"]:
                    arg_name = arg.name if hasattr(arg, "name") else arg.get("name", "")
                    print(f"    - {arg_name}")

    async def execute_prompt(self, prompt_name, args, use_forced_tools):
        """Execute a prompt."""
        server_name = self.mcp_manager.prompt_to_server.get(prompt_name)
        session = self.mcp_manager.sessions.get(server_name)
        if not session:
            print(f"Prompt '{prompt_name}' not found.")
            return

        try:
            result = await session.get_prompt(prompt_name, arguments=args)
            if result and result.messages:
                prompt_content = result.messages[0].content
                text = ""
                if isinstance(prompt_content, str):
                    text = prompt_content
                elif hasattr(prompt_content, "text"):
                    text = prompt_content.text
                else:
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
            print(f"Error executing prompt: {e}")

    async def connect_to_servers_and_run(self):
        """Initialize MCP connections and start chatbot."""
        async with AsyncExitStack() as stack:
            await self.mcp_manager.connect_all(stack)

            # Group capabilities for display
            print("\n📋 Capabilities by server:")
            for s_name, srv_session in self.mcp_manager.sessions.items():
                print(f"\n  🔹 {s_name}:")
                # Tools
                s_tools = [
                    t_name
                    for t_name, srv in self.mcp_manager.tool_to_server.items()
                    if srv == s_name
                ]
                if s_tools:
                    print(f"    Tools: {s_tools}")
                # Resources
                s_resources = [
                    uri
                    for uri, srv in self.mcp_manager.resource_to_server.items()
                    if srv == s_name
                ]
                if s_resources:
                    print(f"    Resources: {s_resources}")

            await self.chat_loop()


async def main():
    chatbot = MCP_ChatBot()
    await chatbot.connect_to_servers_and_run()


if __name__ == "__main__":
    asyncio.run(main())
