# Chat_Unreal Server with Tor, Ollama & Memory
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from typing import Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MEMORY_PATH = os.path.join(BASE_DIR, "chat_memory.json")
LOG_PATH = os.path.join(BASE_DIR, "chat_unreal.log")

DEFAULT_CFG = {
    "model": "darkc0de/XortronCriminalComputingConfig",
    "hf_api_url": "https://api-inference.huggingface.co/models/darkc0de/XortronCriminalComputingConfig",
    "hf_timeout": 120,
    "cache_lifetime_hours": 24,
    "use_tor": True,
    "tor_path": "C:/Program Files/Tor Browser/Browser/TorBrowser/Tor/tor.exe",
}

MAX_HISTORY_ENTRIES = 50
MAX_USER_MESSAGE_LENGTH = 4000
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PROMPT_HISTORY_LIMIT = 12


def log(msg: str) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


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
    if not isinstance(value, str):
        value = ""
    value = CONTROL_CHAR_PATTERN.sub("", value.strip())
    if limit and limit > 0:
        value = value[:limit]
    return value


def _truncate_history(history: Iterable[Dict[str, str]], limit: int) -> List[Dict[str, str]]:
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


def load_config() -> Dict:
    if not os.path.exists(CONFIG_PATH):
        log("Config missing – using defaults.")
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

    merged = DEFAULT_CFG.copy()
    merged.update({k: v for k, v in data.items() if v is not None})
    return merged


def ensure_memory_exists() -> None:
    if not os.path.exists(MEMORY_PATH):
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump({"history": []}, f)


def load_memory() -> Dict:
    with open(MEMORY_PATH, "r", encoding="utf-8-sig") as f:
        raw_mem = _safe_json_loads(f.read()) or {}
    history = raw_mem.get("history", []) if isinstance(raw_mem, dict) else []
    raw_mem["history"] = _truncate_history(history, MAX_HISTORY_ENTRIES)
    return raw_mem


def save_memory(mem: Dict) -> None:
    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2)


TOR_HOST = "127.0.0.1"
TOR_SOCKS_PORT = 9050


def _tor_proxies() -> Dict[str, str]:
    return {
        "http": f"socks5h://{TOR_HOST}:{TOR_SOCKS_PORT}",
        "https": f"socks5h://{TOR_HOST}:{TOR_SOCKS_PORT}",
    }


def _tor_candidates() -> List[str]:
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
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def tor_request(url: str, timeout: int = 20) -> str:
    if not CFG.get("use_tor"):
        return clear_request(url, timeout=timeout)

    if not _is_tor_ready():
        ensure_tor_ready()

    if not _is_tor_ready():
        raise RuntimeError("Tor is not available on the configured SOCKS port.")

    r = requests.get(url, proxies=_tor_proxies(), timeout=timeout)
    r.raise_for_status()
    return r.text


def clear_request(url: str, timeout: int = 15) -> str:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text


def search_web(query: str) -> List[Dict[str, str]]:
    q = query.replace(" ", "+")
    try:
        html = tor_request(f"https://duckduckgo.com/html/?q={q}")
    except Exception as exc:
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
    try:
        if CFG.get("use_tor"):
            text = tor_request(url)
        else:
            text = clear_request(url)
    except Exception as exc:
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
    pattern = r"https?://[\w.-]+\.onion[\w/?=&%-]*"
    return re.findall(pattern, text, flags=re.IGNORECASE)


def build_research_context(message: str) -> str:
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


def launch_tor() -> None:
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
        log(f"Starting Tor using {tor_binary}...")
        try:
            subprocess.Popen(
                [tor_binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            log(f"Failed to launch Tor: {exc}")

    threading.Thread(target=_run_tor, daemon=True).start()


def ensure_tor_ready(timeout: int = 45) -> None:
    if not CFG.get("use_tor"):
        return

    start = time.time()
    while time.time() - start < timeout:
        if _is_tor_ready():
            return
        time.sleep(1)

    log("Tor did not become ready before timeout expired.")


def needs_research(message: str) -> bool:
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


def _extract_hf_text(data) -> str:
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


def query_model(payload: Dict) -> str:
    api_url = (CFG.get("hf_api_url") or "").strip()
    if not api_url:
        model_name = (CFG.get("model") or "").strip()
        if not model_name:
            return "Error: Hugging Face model is not configured."
        api_url = f"https://api-inference.huggingface.co/models/{model_name}"

    timeout = CFG.get("hf_timeout", 120)
    try:
        timeout = max(30, int(timeout))
    except (ValueError, TypeError):
        timeout = 120

    token = os.environ.get("HF_API_TOKEN") or CFG.get("hf_api_token")
    headers = {"Accept": "application/json"}
    if token:
        token_str = str(token).strip()
        if token_str:
            headers["Authorization"] = f"Bearer {token_str}"

    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=timeout)
    except Exception as exc:
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
    mem.setdefault("history", [])
    mem["history"].append(
        {
            "role": _sanitize_text(role, limit=32),
            "content": _sanitize_text(content, limit=MAX_USER_MESSAGE_LENGTH),
        }
    )
    mem["history"] = _truncate_history(mem["history"], MAX_HISTORY_ENTRIES)


CFG = load_config()
ensure_memory_exists()
launch_tor()
ensure_tor_ready()


@app.route("/")
def serve_ui():
    return send_from_directory(BASE_DIR, "Chat_Unreal.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_msg = _sanitize_text(data.get("message", ""), limit=MAX_USER_MESSAGE_LENGTH)
    if not user_msg:
        return jsonify({"response": "No message provided."})

    if len(user_msg) >= MAX_USER_MESSAGE_LENGTH:
        return jsonify({"response": "Message too long. Please shorten your request."})

    mem = load_memory()
    append_history(mem, "user", user_msg)

    context = build_research_context(user_msg) if needs_research(user_msg) else ""
    context = _sanitize_text(context, limit=2000)
    payload = build_model_payload(mem["history"], user_msg, context)
    reply = query_model(payload)

    append_history(mem, "assistant", reply)
    save_memory(mem)
    log(f"User: {user_msg}\nAI: {reply}\n")

    return jsonify({"response": reply})


if __name__ == "__main__":
    print("🔥 Chat_Unreal_V2 running on http://127.0.0.1:4891")
    app.run(host="127.0.0.1", port=4891)
