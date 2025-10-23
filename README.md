# Unreal Coder

## Welcome
Chat Unreal is a friendly research assistant that runs entirely on your computer. It pairs a modern web chat page with a Python server so you can talk to an AI model, keep a running memory of conversations, and (optionally) route web lookups through Tor for extra privacy. No cloud account is required once everything is installed.

---

## Who this guide is for
This README is written for people who may be new to coding. Every section uses plain language, explains unfamiliar terms, and walks through each action one step at a time. Experienced developers will still find the reference details and advanced options in the later sections.

---

## What you will need
Before you begin, make sure you have the following:

1. **A computer running Windows, macOS, or Linux** with an internet connection (only needed for the initial setup).
2. **Python 3.9 or newer.** If you do not already have Python:
   - Windows: download from [python.org/downloads](https://www.python.org/downloads/windows/) and check “Add Python to PATH” during installation.
   - macOS: download from [python.org/downloads](https://www.python.org/downloads/macos/) and follow the installer prompts.
   - Linux: install from your package manager (for example, `sudo apt install python3 python3-venv python3-pip`).
3. **Ollama** installed and running locally. This provides the AI model. Download it from [ollama.com](https://ollama.com/) and follow their installation steps.
4. *(Optional)* **Tor** if you want web research traffic to go through the Tor network. You can skip this if privacy routing is not needed right away.

> **Tip:** If you are unsure whether Python or Ollama are already installed, open a terminal (Command Prompt on Windows, Terminal app on macOS, or your Linux terminal) and type `python --version` or `ollama --version`. If the command is not found, install the missing tool.

---

## Downloading the project
You can obtain the project in two different ways. Choose the option that feels easiest:

### Option A: Download as a ZIP (no Git required)
1. Visit the project page in your web browser.
2. Click the green **Code** button, then choose **Download ZIP**.
3. When the download finishes, unzip the file into a folder you can easily find (for example, `Documents/ChatUnreal`).

### Option B: Clone with Git (for those who already use Git)
```bash
# Replace <your-folder> with the directory where you want the project to live
git clone <repository-url> <your-folder>
cd <your-folder>
```

---

## Quick start (no coding knowledge required)
Follow these steps in order. Each command should be run in the project folder you just downloaded or cloned.

1. **Open a terminal in the project folder.**
   - Windows: open the folder in File Explorer, click the address bar, type `cmd`, and press Enter.
   - macOS: right-click the folder in Finder and choose **New Terminal at Folder** (or open Terminal and use `cd /path/to/folder`).
   - Linux: open your terminal application and use `cd /path/to/folder`.

2. **Create an isolated Python environment (recommended).** This keeps the project’s libraries separate from everything else on your computer.
   ```bash
   python -m venv venv
   ```
   - Windows: activate it with `venv\Scripts\activate`.
   - macOS/Linux: activate it with `source venv/bin/activate`.
   You will know the environment is active when you see `(venv)` at the start of your terminal line.

3. **Install the required Python libraries.**
   ```bash
   pip install flask requests beautifulsoup4
   ```
   These packages let the server run, perform web lookups, and process the results.

4. **Check your Ollama model.** Open Ollama and make sure at least one model (for example, `llama3`) is downloaded and ready. Keep the Ollama service running.

5. **Review the configuration file.** Open `config.json` in a simple text editor (Notepad, TextEdit, or any editor you prefer) and confirm:
   - `"model"` matches the Ollama model you want to use.
   - `"use_tor"` is `false` unless you have Tor installed and configured.
   - `"tor_path"` points to the Tor executable if you plan to enable Tor later.

6. **Start the server.**
   ```bash
   python Chat_Unreal_Server.py
   ```
   Keep this terminal window open. When it says the server is running, you are ready to chat.

7. **Open the chat page.** Launch your web browser and go to [http://127.0.0.1:4891](http://127.0.0.1:4891). You should see the Chat Unreal interface. Type a message and press **Send** to begin.

> **Stopping everything:** When you finish, close the browser tab and press `Ctrl+C` in the terminal to stop the server. Deactivate the virtual environment with `deactivate` (or simply close the terminal window).

---

## Understanding the project layout
```
.
├── Chat_Unreal_Server.py   # Python server that powers the chat and optional Tor research
├── Chat_Unreal.html        # Web page displayed in your browser
├── static/
│   ├── style.css           # Visual appearance of the chat page
│   └── script.js           # Browser-side chat logic
├── config.json             # User-editable settings (model name, Tor options)
├── chat_memory.json        # Stores recent conversations
├── chat_unreal.log         # Activity log for debugging or auditing
└── run.ps1                 # Windows PowerShell launcher (optional)
```

### Key files in plain language
- **Chat_Unreal_Server.py:** The engine. It listens for chat messages and sends them to Ollama. If Tor is enabled, it routes research queries through Tor.
- **Chat_Unreal.html:** The front-end page you interact with. It uses the files in `static/` for styling and behaviour.
- **config.json:** Your main control panel. Change the AI model or toggle privacy features here.
- **chat_memory.json & chat_unreal.log:** Automatically created files that keep a history of conversations. You can delete them at any time to reset the memory or clear logs.

---

## Optional: enabling Tor privacy routing
1. Install Tor (for example, the Tor Browser bundle or the tor expert bundle).
2. Locate the Tor executable on your system.
3. Update `config.json`:
   ```json
   {
     "model": "llama3",
     "cache_lifetime_hours": 0,
     "use_tor": true,
     "tor_path": "C:/Path/To/Tor/tor.exe"
   }
   ```
4. Restart the Chat Unreal server. On startup it will launch Tor and wait until the secure connection is ready before processing research requests.

> **Safety note:** Tor adds privacy but may slow down web lookups. Only enable it if you understand how Tor works and trust the network environment.

---

## Troubleshooting checklist
- **The terminal says a command is not recognized.** Double-check that Python or pip was installed and added to your PATH. Re-open the terminal after installing.
- **The server starts but the web page will not load.** Make sure you are visiting `http://127.0.0.1:4891` (not `https`). Refresh the page after the server reports it is running.
- **Responses mention missing models.** Confirm the `model` value in `config.json` matches a model that is already downloaded in Ollama (`ollama list`).
- **Tor will not start.** Verify the `tor_path` is correct and that your security software allows Tor to run.

If you get stuck, copy the exact error message and search for it online or reach out in the project’s issue tracker with as much detail as possible.

---

## Next steps and customization
- Personalize the look and feel by editing `static/style.css`.
- Enhance the chat behaviour or add new endpoints by editing `Chat_Unreal_Server.py`.
- Integrate with other tools or dashboards by calling the `/api/chat` endpoint from your own applications.

We hope you enjoy exploring Chat Unreal! Feel free to open an issue or submit a pull request with feedback or improvements.
