"""Chat_Unreal Server with Tor, Hugging Face integration, and persistent memory."""

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from flask import Flask, Response, jsonify, request, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MEMORY_PATH = os.path.join(BASE_DIR, "chat_memory.json")
LOG_BASENAME = "chat_unreal.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MiB per log file

DEFAULT_CFG = {
    "model": "darkc0de/XortronCriminalComputingConfig",
    "hf_api_url": "https://router.huggingface.co/hf-inference/models/darkc0de/XortronCriminalComputingConfig",
    "hf_timeout": 120,
    "cache_lifetime_hours": 24,
    "use_tor": True,
    "tor_path": "C:/Program Files/Tor Browser/Browser/TorBrowser/Tor/tor.exe",
}

KNOWN_CONFIG_KEYS = {
    "model",
    "hf_api_url",
    "hf_timeout",
    "cache_lifetime_hours",
    "use_tor",
    "tor_path",
    "hf_api_token",
    "default_model",
}

MAX_HISTORY_ENTRIES = 50
MAX_USER_MESSAGE_LENGTH = 4000
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_HISTORY_LIMIT = 12
TOR_HOST = "127.0.0.1"
TOR_SOCKS_PORT = 9050


def _current_log_path() -> str:
    """Return the path to the active log file, using a daily suffix for rotation."""

    dated_name = f"{os.path.splitext(LOG_BASENAME)[0]}_{datetime.utcnow():%Y%m%d}.log"
    return os.path.join(BASE_DIR, dated_name)


def _rotate_logs_if_needed() -> None:
    """Rotate the active log file once it grows too large."""

    path = _current_log_path()
    if not os.path.exists(path):
        return
    try:
        size = os.path.getsize(path)
    except OSError:
        return
    if size <= LOG_MAX_BYTES:
        return
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    rotated = f"{path}.{timestamp}"
    try:
        shutil.move(path, rotated)
        # Added: Notify about log rotation in the new file.
    except OSError:
        return
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Log rotated to {rotated}\n")
    except OSError:
        pass


def log(msg: str) -> None:
    """Append a timestamped entry to the rotating log file."""

    _rotate_logs_if_needed()
    try:
        with open(_current_log_path(), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def _safe_json_loads(raw: str) -> Dict:
    """Attempt to load JSON while tolerating BOMs and trailing data."""

    if not raw:
        return {}

    raw = raw.lstrip("\ufeff").strip()
    if not raw:
        return {}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        try:
            obj, _ = decoder.raw_decode(raw)
            return obj
        except json.JSONDecodeError:
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
            raise


def _sanitize_text(value: str, limit: Optional[int] = None) -> str:
    """Normalize incoming text by trimming control characters and applying limits."""

    if not isinstance(value, str):
        value = ""
    value = CONTROL_CHAR_PATTERN.sub("", value.strip())
    if limit and limit > 0:
        value = value[:limit]
    return value


def _truncate_history(history: Iterable[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
    """Clip memory history to a maximum size while sanitizing entries."""

    cleaned: List[Dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = _sanitize_text(item.get("role", ""), limit=32)
        content = _sanitize_text(item.get("content", ""), limit=MAX_USER_MESSAGE_LENGTH)
        if not role or not content:
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned[-limit:]


def _write_example_config() -> None:
    """Create a starter config.json file with safe defaults if missing."""

    example = DEFAULT_CFG.copy()
    example.setdefault("hf_api_token", "")
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(example, f, indent=2)
    except OSError as exc:
        log(f"Failed to generate example config.json: {exc}")


def load_config() -> Dict:
    """Load configuration, generating an example and validating keys when needed."""

    if not os.path.exists(CONFIG_PATH):
        log("Config missing – generating example config.json with defaults.")
        _write_example_config()
        return DEFAULT_CFG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            raw = f.read()
    except OSError as exc:
        log(f"Failed to read config: {exc}")
        return DEFAULT_CFG.copy()

    try:
        data = _safe_json_loads(raw)
    except json.JSONDecodeError as exc:
        log(f"Invalid config JSON ({exc}) – using defaults.")
        return DEFAULT_CFG.copy()

    if not isinstance(data, dict):
        log("Config file did not contain a JSON object – using defaults.")
        return DEFAULT_CFG.copy()

    merged = DEFAULT_CFG.copy()
    merged.update({k: v for k, v in data.items() if v is not None})

    unknown_keys = set(data.keys()) - KNOWN_CONFIG_KEYS
    if unknown_keys:
        log(f"Unknown config keys ignored: {sorted(unknown_keys)}")

    return merged


def ensure_memory_exists() -> None:
    """Guarantee that the memory store file exists on disk."""

    if os.path.exists(MEMORY_PATH):
        return
    try:
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump({"history": []}, f)
    except OSError as exc:
        log(f"Failed to initialize memory file: {exc}")


def load_memory() -> Dict:
    """Read persisted conversation memory with sanitization."""

    try:
        with open(MEMORY_PATH, "r", encoding="utf-8-sig") as f:
            raw_mem = _safe_json_loads(f.read()) or {}
    except OSError as exc:
        log(f"Failed to load memory file: {exc}")
        return {"history": []}

    history = raw_mem.get("history", []) if isinstance(raw_mem, dict) else []
    raw_mem["history"] = _truncate_history(history, MAX_HISTORY_ENTRIES)
    return raw_mem


def save_memory(mem: Dict) -> None:
    """Persist the conversation memory safely."""

    try:
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2)
    except OSError as exc:
        log(f"Failed to save memory: {exc}")


def _tor_proxies() -> Dict[str, str]:
    """Construct the SOCKS proxy mapping for Tor traffic."""

    return {
        "http": f"socks5h://{TOR_HOST}:{TOR_SOCKS_PORT}",
        "https": f"socks5h://{TOR_HOST}:{TOR_SOCKS_PORT}",
    }


def _tor_candidates() -> List[str]:
    """Return potential filesystem locations for the Tor binary."""

    candidates: List[str] = []
    configured = CFG.get("tor_path") if "CFG" in globals() else None
    env_override = os.environ.get("TOR_PATH")

    for path in [configured, env_override]:
        if path and path not in candidates:
            candidates.append(path)

    default_paths = [
        "tor",
        "/usr/bin/tor",
        "/usr/local/bin/tor",
    ]

    program_files = os.environ.get("PROGRAMFILES")
    local_app_data = os.environ.get("LOCALAPPDATA")
    windows_suffix = os.path.join(
        "Tor Browser",
        "Browser",
        "TorBrowser",
        "Tor",
        "tor.exe",
    )
    for base in [program_files, local_app_data]:
        if base:
            default_paths.append(os.path.join(base, windows_suffix))

    for candidate in default_paths:
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _resolve_tor_binary() -> Optional[str]:
    """Locate an executable Tor binary from config, environment, or defaults."""

    for candidate in _tor_candidates():
        if not candidate:
            continue
        if os.path.isabs(candidate) and os.path.exists(candidate):
            return candidate
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    return None


def _is_tor_ready(host: str = TOR_HOST, port: int = TOR_SOCKS_PORT) -> bool:
    """Check whether the Tor SOCKS proxy port currently accepts connections."""

    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _http_request(url: str, timeout: int, proxies: Optional[Dict[str, str]] = None) -> str:
    """Perform a GET request with shared error handling semantics."""

    try:
        response = requests.get(url, timeout=timeout, proxies=proxies)
        response.raise_for_status()
        return response.text
    except requests.RequestException as exc:
        log(f"HTTP request failed for {url}: {exc}")
        raise RuntimeError(f"Request to {url} failed: {exc}") from exc


def tor_request(url: str, timeout: int = 20) -> str:
    """Fetch a URL through the Tor network, falling back gracefully."""

    if not CFG.get("use_tor"):
        return clear_request(url, timeout=timeout)

    if not _is_tor_ready():
        ensure_tor_ready()

    if not _is_tor_ready():
        log("Tor is not available on the configured SOCKS port.")
        raise RuntimeError("Tor is unavailable; please verify Tor is running.")

    return _http_request(url, timeout, proxies=_tor_proxies())


def clear_request(url: str, timeout: int = 15) -> str:
    """Perform a direct HTTP request without Tor."""

    return _http_request(url, timeout, proxies=None)


def search_web(query: str) -> List[Dict[str, str]]:
    """Search DuckDuckGo via Tor and return the top result metadata."""

    q = query.replace(" ", "+")
    try:
        html = tor_request(f"https://duckduckgo.com/html/?q={q}")
    except Exception as exc:  # noqa: BLE001
        log(f"Web search via Tor failed: {exc}")
        return []
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, str]] = []
    for a in soup.select("a.result__a")[:5]:
        href = a.get("href")
        if not href:
            continue
        results.append({"title": a.get_text(strip=True), "url": href})
    return results


def fetch_article(url: str) -> str:
    """Retrieve and sanitize article content for research context."""

    try:
        if CFG.get("use_tor"):
            text = tor_request(url)
        else:
            text = clear_request(url)
    except Exception as exc:  # noqa: BLE001
        log(f"Failed to fetch article {url}: {exc}")
        return ""

    soup = BeautifulSoup(text, "html.parser")
    for element in soup(["script", "style", "noscript"]):
        element.decompose()
    content = " ".join(
        chunk.strip() for chunk in soup.get_text(separator="\n").splitlines() if chunk.strip()
    )
    return content[:2000]


def extract_onion_links(text: str) -> List[str]:
    """Pull onion service URLs from arbitrary text."""

    pattern = r"https?://[\w.-]+\.onion[\w/?=&%-]*"
    return re.findall(pattern, text, flags=re.IGNORECASE)


def build_research_context(message: str) -> str:
    """Assemble relevant research snippets to feed into the model prompt."""

    context_parts: List[str] = []
    results = search_web(message)
    if results:
        top_titles = "; ".join(r["title"] for r in results)
        context_parts.append(f"Top results: {top_titles}.")
        for item in results[:3]:
            article = fetch_article(item["url"])
            if article:
                context_parts.append(f"{item['title']}: {article}")

    for onion_url in extract_onion_links(message):
        article = fetch_article(onion_url)
        if article:
            context_parts.append(f"Onion source {onion_url}: {article}")

    return "\n\n".join(context_parts)


def needs_research(message: str) -> bool:
    """Heuristic to decide whether a prompt should trigger research scraping."""

    normalized_msg = message.lower()
    research_keywords = [
        "search",
        "find",
        "lookup",
        "web",
        "research",
        "investigate",
        "deep dive",
        "tor",
        "dark web",
    ]
    return any(keyword in normalized_msg for keyword in research_keywords)


def _format_prompt(history: List[Dict[str, str]], user_msg: str, context: str) -> str:
    """Craft the text prompt for the Hugging Face inference endpoint."""

    trimmed_history = _truncate_history(history, PROMPT_HISTORY_LIMIT)
    prompt_segments: List[str] = [
        (
            "System: You are Chat Unreal, a precise, security-conscious coding assistant. "
            "You produce hardened, production-ready answers with detailed reasoning "
            "and rely on the Hugging Face model darkc0de/XortronCriminalComputingConfig "
            "for every coding task."
        )
    ]
    if context:
        prompt_segments.append(f"Context: {context}")

    for entry in trimmed_history:
        role = entry.get("role", "").lower()
        prefix = "Assistant" if role == "assistant" else "User"
        prompt_segments.append(f"{prefix}: {entry.get('content', '')}")

    prompt_segments.append(f"User: {user_msg}")
    prompt_segments.append("Assistant:")
    return "\n\n".join(segment for segment in prompt_segments if segment)


def build_model_payload(history: List[Dict[str, str]], user_msg: str, context: str) -> Dict:
    """Create the payload sent to the Hugging Face inference endpoint."""

    prompt = _format_prompt(history, user_msg, context)
    return {
        "inputs": prompt,
        "parameters": {
            "temperature": 0.2,
            "max_new_tokens": 800,
            "top_p": 0.9,
            "return_full_text": False,
        },
        "options": {"wait_for_model": True},
    }


_TOKEN_WARNING_EMITTED = False
_MISSING_TOKEN_LOGGED = False


def _warn_windows_export() -> None:
    """Log guidance for Windows users who mistakenly use bash-style export."""

    global _TOKEN_WARNING_EMITTED
    if _TOKEN_WARNING_EMITTED or os.name != "nt":
        return
    _TOKEN_WARNING_EMITTED = True
    log("HF_API_TOKEN missing. On PowerShell use: $env:HF_API_TOKEN = 'your_token_here'")


def _load_hf_token() -> Optional[str]:
    """Return the Hugging Face token from environment or config, if available."""

    token_sources = [
        os.environ.get("HF_API_TOKEN"),
        os.environ.get("hf_api_token"),
        os.environ.get("HF-HUB_TOKEN"),
        CFG.get("hf_api_token"),
    ]
    for token in token_sources:
        if token and str(token).strip():
            return str(token).strip()
    _warn_windows_export()
    return None


def _resolve_model_name(override: Optional[str]) -> str:
    """Choose the Hugging Face model name from override, config, or defaults."""

    if override and override.strip():
        return override.strip()
    if CFG.get("default_model"):
        return str(CFG.get("default_model")).strip()
    return str(CFG.get("model", DEFAULT_CFG["model"])).strip()


def _build_hf_url(model_name: str, explicit_url: Optional[str]) -> str:
    """Construct the Hugging Face inference URL from config and model name."""

    if explicit_url and explicit_url.strip():
        return explicit_url.strip()
    clean_model = model_name.strip()
    return f"https://router.huggingface.co/hf-inference/models/{clean_model}"


def _prepare_hf_headers(token: Optional[str]) -> Dict[str, str]:
    """Assemble request headers for Hugging Face calls."""

    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_hf_text(data) -> str:
    """Normalize Hugging Face responses to a plain text string."""

    if isinstance(data, dict):
        for key in ("generated_text", "text", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if "choices" in data and isinstance(data["choices"], list):
            texts = [_extract_hf_text(choice) for choice in data["choices"]]
            return "\n".join(t for t in texts if t)
        if "data" in data and isinstance(data["data"], list):
            texts = [_extract_hf_text(item) for item in data["data"]]
            return "\n".join(t for t in texts if t)
        return ""
    if isinstance(data, list):
        texts = [_extract_hf_text(item) for item in data]
        return "\n".join(t for t in texts if t)
    if isinstance(data, str):
        return data
    return ""


def query_model(payload: Dict, model_override: Optional[str] = None) -> str:
    """Send a prompt payload to Hugging Face and return the generated text."""

    global _MISSING_TOKEN_LOGGED

    model_name = _resolve_model_name(model_override or "")
    api_url = _build_hf_url(model_name, CFG.get("hf_api_url"))

    timeout = CFG.get("hf_timeout", 120)
    try:
        timeout = max(30, int(timeout))
    except (ValueError, TypeError):
        timeout = 120

    token = _load_hf_token()
    headers = _prepare_hf_headers(token)

    if token is None:
        if not _MISSING_TOKEN_LOGGED:
            log("HF_API_TOKEN missing – operating in local-only mode.")
            _MISSING_TOKEN_LOGGED = True
        return "Model not available: configure HF_API_TOKEN for remote inference."

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        log(f"Model request failed: {exc}")
        return "Error: Unable to contact the Hugging Face inference endpoint."

    if response.status_code == 401:
        log("Model request unauthorized – verify the HF_API_TOKEN environment variable.")
        return "Error: Hugging Face authorization failed. Set a valid HF_API_TOKEN."
    if response.status_code == 503:
        return "The model is loading on Hugging Face. Please retry in a few seconds."

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        preview = response.text[:500]
        log(f"Model HTTP error: {exc}; payload preview: {preview}")
        return "Error: Model endpoint returned an unexpected response."

    data = _safe_json_loads(response.text) if response.text else {}
    text = _extract_hf_text(data).strip()
    if not text:
        log(f"Empty Hugging Face response: {data}")
        return "Error: Received an empty response from the Hugging Face model."

    return text


def append_history(mem: Dict, role: str, content: str) -> None:
    """Append a sanitized entry to the memory history buffer."""

    mem.setdefault("history", [])
    mem["history"].append(
        {
            "role": _sanitize_text(role, limit=32),
            "content": _sanitize_text(content, limit=MAX_USER_MESSAGE_LENGTH),
        }
    )
    mem["history"] = _truncate_history(mem["history"], MAX_HISTORY_ENTRIES)


def launch_tor() -> None:
    """Attempt to start a Tor process if configured and not already running."""

    if not CFG.get("use_tor"):
        return

    if _is_tor_ready():
        log("Tor already running on the configured SOCKS port.")
        return

    tor_binary = _resolve_tor_binary()
    if not tor_binary:
        log("Tor binary could not be located. Set 'tor_path' in config.json or TOR_PATH env var.")
        return

    def _run_tor() -> None:
        """Launch Tor asynchronously while suppressing noisy output."""

        log(f"Starting Tor using {tor_binary}...")
        try:
            subprocess.Popen(
                [tor_binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            log(f"Failed to launch Tor: {exc}")

    threading.Thread(target=_run_tor, daemon=True).start()


def ensure_tor_ready(timeout: int = 45) -> None:
    """Wait for Tor to expose its SOCKS proxy before continuing."""

    if not CFG.get("use_tor"):
        return

    start = time.time()
    while time.time() - start < timeout:
        if _is_tor_ready():
            return
        time.sleep(1)

    log("Tor did not become ready before timeout expired.")


def _tor_health_status() -> Tuple[str, str]:
    """Return a tuple of Tor status label and explanatory detail."""

    if not CFG.get("use_tor"):
        return "disabled", "Tor usage disabled in configuration."
    if _is_tor_ready():
        return "ready", "Tor proxy reachable."
    return "unavailable", "Tor proxy not reachable."


def _huggingface_health_status() -> Tuple[str, str]:
    """Probe Hugging Face reachability for the configured model."""

    model_name = _resolve_model_name(None)
    api_url = _build_hf_url(model_name, CFG.get("hf_api_url"))
    token = _load_hf_token()
    if token is None:
        return "token-missing", "HF_API_TOKEN not configured."
    headers = _prepare_hf_headers(token)

    try:
        response = requests.head(api_url, headers=headers, timeout=5)
    except requests.RequestException as exc:
        log(f"Hugging Face health check failed: {exc}")
        return "offline", str(exc)

    if response.status_code == 200:
        return "online", "Status code 200"
    if response.status_code == 401:
        return "unauthorized", "Status code 401"
    if response.status_code in (405, 503):
        return "reachable", f"Status code {response.status_code}"

    return "error", f"Unexpected status {response.status_code}"


def gather_health_status() -> Dict[str, Dict[str, str]]:
    """Collect service health information for the /health endpoint."""

    tor_state, tor_detail = _tor_health_status()
    hf_state, hf_detail = _huggingface_health_status()
    return {
        "tor": {"status": tor_state, "detail": tor_detail},
        "huggingface": {"status": hf_state, "detail": hf_detail},
    }


CFG = load_config()
ensure_memory_exists()
launch_tor()
ensure_tor_ready()


@app.route("/")
def serve_ui():
    """Serve the static HTML interface."""

    return send_from_directory(BASE_DIR, "Chat_Unreal.html")


@app.route("/health", methods=["GET"])
def health() -> Tuple[Response, int]:
    """Report simple service health diagnostics."""

    status = gather_health_status()
    return jsonify(status), 200


@app.route("/api/chat", methods=["POST"])
def chat():
    """Primary chat endpoint orchestrating research, memory, and model calls."""

    data = request.get_json(silent=True) or {}
    user_msg = _sanitize_text(data.get("message", ""), limit=MAX_USER_MESSAGE_LENGTH)
    if not user_msg:
        return jsonify({"response": "No message provided."})

    if len(user_msg) >= MAX_USER_MESSAGE_LENGTH:
        return jsonify({"response": "Message too long. Please shorten your request."})

    requested_model = _sanitize_text(data.get("model", ""), limit=128)

    mem = load_memory()
    append_history(mem, "user", user_msg)

    context = build_research_context(user_msg) if needs_research(user_msg) else ""
    context = _sanitize_text(context, limit=2000)
    payload = build_model_payload(mem["history"], user_msg, context)
    reply = query_model(payload, model_override=requested_model)

    append_history(mem, "assistant", reply)
    save_memory(mem)
    log(f"User: {user_msg}\nAI: {reply}\n")

    return jsonify({"response": reply})


if __name__ == "__main__":
    print("🔥 Chat_Unreal_V2 running on http://127.0.0.1:4891")
    app.run(host="127.0.0.1", port=4891)
