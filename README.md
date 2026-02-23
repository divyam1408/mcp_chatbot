# MCP Chatbot & Research Tool

A powerful AI assistant built with the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) that connects to external tools and resources. This project demonstrates a modular client-server architecture supporting multiple transports and dynamic tool discovery.

## 🚀 Features

-   **Modular Client Architecture**: Decouples chat logic from connection management via `MCPClientManager`.
-   **Multi-Server Support**: Connects to multiple MCP servers simultaneously.
-   **Expanded Transports**: Supports `stdio` (local), `sse` (standard hosted), and `http` (modern streamable HTTP) protocols.
-   **Dynamic Tool Shortcuts**: 
    -   `@<tool_name> <args>`: Automatically maps positional arguments to any tool's schema.
    -   `@git <command> <args>`: Natural shorthand for GitHub operations.
-   **Dual Operation Modes**:
    1.  **Optional Tool Mode**: LLM intelligently decides when to use tools.
    2.  **Forced Tool Mode**: Enforces a rigid research workflow (Search → Extract → Summarize).
-   **Comprehensive MCP Discovery**: Automatically lists and manages Tools, Resources, and Prompts from all connected servers.

## 🏗️ Architecture

The project follows a **Client-Host-Server** architecture:

1.  **Client/Host (Chatbot)**: `mcp_chatbot.py` manages the UI and LLM interaction.
2.  **Manager**: `mcp_client_manager.py` capsules all session management, configuration loading, and transport handling.
3.  **Servers**: Independent processes or remote services (e.g., `research_server.py`, GitHub MCP, Fetch MCP).
4.  **Communication**: Uses JSON-RPC over `stdio`, `sse`, or `http` as defined in the configuration.

## 📂 Project Components

-   **`mcp_chatbot.py`**: The main interface.
-   **`mcp_client_manager.py`**: The core logic for server connections and tool routing.
-   **`research_server.py`**: A local stdio-based research server.
-   **`servers.json`**: Central configuration for all MCP servers.
-   **`.github/workflows/lint.yml`**: CI pipeline for automated linting and formatting.

## 🛠️ Installation

1.  **Prerequisites**: Python 3.12+ and `uv` package manager.
2.  **Install Dependencies**:
    ```bash
    uv sync
    ```
3.  **Environment Setup**:
    Create a `.env` file:
    ```env
    HUGGINGFACE_API_KEY=your_key_here
    GITHUB_TOKEN=your_optional_github_token
    ```

## 🏃 Usage

### Running the Chatbot
```bash
uv run mcp_chatbot.py
```

### Generic Commands
-   **Tool Shortcut**: `@fetch https://google.com` (Maps to `fetch` tool).
-   **Git Shortcut**: `@git list_commits owner=divyam1408 repo=mcp_chatbot`.
-   **Resource Shortcut**: `@folders` (Reads `papers://folders`).
-   **Prompt Command**: `/prompt generate_search_prompt topic=quantum`.

## 🤖 CI/CD

This project uses **Ruff** for automated code quality:
-   **Linting**: `uvx ruff check .`
-   **Formatting**: `uvx ruff format .`
-   Checks are automatically run on every push via GitHub Actions.
