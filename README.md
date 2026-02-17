# MCP Chatbot & Research Tool

A powerful AI assistant built with the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) that connects to external tools and resources. This project demonstrates a client-server architecture where a chatbot client interacts with specialized MCP servers (like a research paper server).

## 🚀 Features

-   **Multi-Server Support**: Connects to multiple MCP servers simultaneously via configuration.
-   **Dual Operation Modes**:
    1.  **Optional Tool Mode**: The model intelligently decides when to use tools.
    2.  **Forced Tool Mode**: Enforces a specific workflow (Search → Extract → Summarize).
-   **Comprehensive MCP Support**:
    -   **Tools**: Executable functions (e.g., searching arXiv).
    -   **Resources**: Read-only data sources (e.g., paper summaries, folders).
    -   **Prompts**: Pre-defined templates for interactions (e.g., complex search strategies).
-   **Interactive Commands**:
    -   `@topic`: Quickly access resource templates (e.g., `@physics` reads `papers://physics`).
    -   `/prompts`: List available prompts.
    -   `/prompt <name> <args>`: Execute a specific prompt.

## 📂 Project Components

### 1. `mcp_chatbot.py` (The Client)
The main interface. It initializes an AI client (using `aisuite`), connects to servers defined in `servers.json`, and manages the chat loop. It handles:
-   Tool execution and routing.
-   Resource retrieval (static and templates).
-   Prompt execution.

### 2. `research_server.py` (The Server)
An MCP server implementation focusing on academic research.
-   **Tools**:
    -   `search_papers(topic, max_results)`: Searches arXiv and saves metadata.
    -   `extract_info(paper_id)`: Retrieves details for a specific paper.
-   **Resources**:
    -   `papers://folders`: Lists available search topics.
    -   `papers://{topic}`: Returns stored papers for a topic.
-   **Prompts**:
    -   `generate_search_prompt`: A template to guide the model in researching a topic.

### 3. `servers.json` (Configuration)
Defines the MCP servers the client should connect to.
```json
{
  "servers": [
    {
      "name": "research",
      "command": "uv",
      "args": ["run", "research_server.py"],
      "env": null
    }
  ]
}
```

## 🛠️ Installation

1.  **Prerequisites**:
    -   Python 3.12+
    -   `uv` package manager (recommended) or `pip`

2.  **Install Dependencies**:
    ```bash
    uv sync
    # OR
    pip install -r requirements.txt
    ```

3.  **Environment Setup**:
    Create a `.env` file in the root directory:
    ```env
    HUGGINGFACE_API_KEY=your_key_here
    ```
    (Note: The project is configured to use `huggingface:Qwen/Qwen3-8B` via `aisuite`, but you can change the model in `mcp_chatbot.py`.)

## 🏃 Usage

### Running the Chatbot
Start the chatbot client. It will automatically start the configured servers (like `research_server.py`) as subprocesses.

```bash
uv run mcp_chatbot.py
```

### interacting with the Chatbot

1.  **Mode Selection**:
    At startup, choose between:
    -   **Mode 1**: Standard chat where the AI decides to use tools.
    -   **Mode 2**: Forced workflow for deep research (Search -> Extract).

2.  **Commands**:
    -   **Standard Query**: "Find papers about massive black holes."
    -   **View Resources**: Type `@physics` to load papers on physics (if previously searched).
    -   **List Prompts**: Type `/prompts`.
    -   **Run Prompt**: Type `/prompt generate_search_prompt topic=quantum_computing`.

## 🏗️ Extending

To add a new MCP server:
1.  Create your server script (e.g., `my_server.py`).
2.  Add it to `servers.json`:
    ```json
    {
      "name": "my_new_server",
      "command": "uv",
      "args": ["run", "my_server.py"],
      "env": null
    }
    ```
3.  Restart `mcp_chatbot.py`.
