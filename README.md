# Chat Unreal

Unreal_Ai is a lightweight research assistant that blends a browser-based chat experience with a Python back end. The Flask server orchestrates conversation memory, optional privacy-preserving web lookups through Tor, and streaming interactions with an Ollama model running locally. The front end provides a clean single-page chat client styled with modern gradients and responsive layout.

## Features

- **Full-stack chat experience** – `Chat_Unreal.html` plus bundled CSS/JavaScript deliver a polished chat UI that talks directly to the Flask API.
- **Local model integration** – Proxies every user exchange to an Ollama-compatible chat endpoint configured in `config.json`.
- **Persistent memory** – Stores the last several user/assistant turns in `chat_memory.json` so the assistant can respond with continuity.
- **Optional Tor support** – When enabled, outbound web searches are routed through Tor for an additional layer of privacy.
- **Web research assist** – Detects natural-language requests to "search", "find", or "lookup" and adds contextual snippets from DuckDuckGo.
- **Structured logging** – Logs every interaction to `chat_unreal.log` for later analysis or auditing.

## Project layout

```
.
├── Chat_Unreal_Server.py   # Flask application with Tor-aware search and Ollama relay
├── Chat_Unreal.html        # Single-page chat client served by Flask
├── static/
│   ├── style.css           # Visual design for the chat experience
│   └── script.js           # Front-end chat logic and API integration
├── config.json             # Runtime configuration for Tor and model selection
├── chat_memory.json        # Persistent conversation history
├── chat_unreal.log         # Rolling server log of conversations
└── run.ps1                 # Convenience launcher for Windows environments
```

## Prerequisites

- Python 3.9 or newer
- [Ollama](https://ollama.com/) running locally with the model specified in `config.json`
- (Optional) A Tor binary if you plan to enable Tor routing for search queries

You can use the provided `venv` directory or create your own virtual environment.

## Installation

```bash
# Clone the repository
 git clone <your-fork-url>
 cd Unreal_Ai

# (Optional) Create and activate a virtual environment
 python -m venv .venv
 source .venv/bin/activate  # On Windows use: .venv\\Scripts\\activate

# Install Python dependencies
 pip install -r requirements.txt  # If you maintain your own requirements file
# or install the minimal set manually
 pip install flask requests beautifulsoup4
```

If you plan to rely on Tor, ensure it is installed locally and that you know the absolute path to the executable. On Windows the example path in `config.json` points to the Chocolatey installation of the Tor Browser bundle.

## Configuration

All runtime options live in `config.json`:

| Key | Description |
| --- | --- |
| `model` | The Ollama model name that the server will pass to `http://localhost:11434/api/chat` (for example, `llama3` or `chatunreal`). |
| `cache_lifetime_hours` | Reserved for future caching behaviour (currently unused but retained for compatibility). |
| `use_tor` | Boolean flag; when `true`, web searches are proxied through Tor. |
| `tor_path` | Absolute path to the Tor executable. Required only if `use_tor` is enabled. |

Update the file to match your environment. For cross-platform setups, consider maintaining separate configuration files (for example `config.windows.json`, `config.linux.json`) and copying the appropriate one before launching the server.

## Running the server

1. Ensure your Ollama daemon is running and serving requests on `http://localhost:11434`.
2. Activate your Python environment.
3. Launch the Flask server:

   ```bash
   python Chat_Unreal_Server.py
   ```

   The application starts on `http://127.0.0.1:4891` by default. The console prints a banner once Flask is ready.

If Tor support is enabled, the server will attempt to start Tor in a background thread during initialisation. *** Use a VPN ***

### Using the chat client

- Navigate to `http://127.0.0.1:4891/` in your browser.
- Type a message in the input field and press **Send** (or hit **Enter**).
- The assistant responds using the selected Ollama model and supplements responses with recent conversation context stored in `chat_memory.json`.
- To trigger a web-assisted answer, include language such as "search for", "find information on", or "lookup" in your prompt.

### API access

If you prefer to integrate the back end with another client, POST JSON payloads directly to `/api/chat`:

```http
POST /api/chat
Content-Type: application/json

{ "message": "Explain how Tor integration works." }
```

The response envelope contains a single `response` field with the assistant's reply.

## Data and logs

- **Conversation memory** – `chat_memory.json` keeps a running list of turns. Clear or delete the file to reset the assistant's memory.
- **Logs** – `chat_unreal.log` captures timestamps, user prompts, and AI replies. Rotate or archive this file regularly to manage disk usage.

## Development tips

- Use `static/script.js` to adjust the front-end behaviour (for example, adding streaming responses or Markdown rendering).
- Update `static/style.css` to customise branding, colour schemes, or layout.
- Extend `Chat_Unreal_Server.py` to add authentication, alternative search providers, or richer context injection.

Contributions, issues, and suggestions are welcome. Happy hacking!

