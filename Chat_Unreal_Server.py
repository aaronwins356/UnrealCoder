# Chat_Unreal Server with Tor, Ollama & Memory
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MEMORY_PATH = os.path.join(BASE_DIR, "chat_memory.json")
LOG_PATH = os.path.join(BASE_DIR, "chat_unreal.log")

DEFAULT_CFG = {
    "model": "chatunreal",
    "cache_lifetime_hours": 24,
    "use_tor": True,
    "tor_path": "C:/Program Files/Tor Browser/Browser/TorBrowser/Tor/tor.exe",
}


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
        return _safe_json_loads(f.read()) or {"history": []}


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


def build_model_payload(history: List[Dict[str, str]], user_msg: str, context: str) -> Dict:
    system_prompt = {
        "role": "system",
        "content": "You are Chat Unreal, a factual, step-by-step instructional AI.",
    }
    messages = [system_prompt] + history[-8:] + [
        {"role": "user", "content": f"{context}\n\n{user_msg}".strip()}
    ]
    return {
        "model": CFG["model"],
        "messages": messages,
        "stream": False,
    }


def query_local_model(payload: Dict) -> str:
    try:
        r = requests.post(
            "http://localhost:11434/api/chat",
            json=payload,
            timeout=120,
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        response_json = _safe_json_loads(r.text)
        return response_json.get("message", {}).get("content", "No response.")
    except Exception as exc:
        log(f"Model request failed: {exc}")
        return "Error: Unable to retrieve a response from the local model."


def append_history(mem: Dict, role: str, content: str) -> None:
    mem.setdefault("history", []).append({"role": role, "content": content})
    if len(mem["history"]) > 50:
        mem["history"] = mem["history"][-50:]


CFG = load_config()
ensure_memory_exists()
launch_tor()
ensure_tor_ready()


@app.route("/")
def serve_ui():
    return send_from_directory(BASE_DIR, "Chat_Unreal.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json or {}
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"response": "No message provided."})

    mem = load_memory()
    append_history(mem, "user", user_msg)

    context = build_research_context(user_msg) if needs_research(user_msg) else ""
    payload = build_model_payload(mem["history"], user_msg, context)
    reply = query_local_model(payload)

    append_history(mem, "assistant", reply)
    save_memory(mem)
    log(f"User: {user_msg}\nAI: {reply}\n")

    return jsonify({"response": reply})


if __name__ == "__main__":
    print("🔥 Chat_Unreal_V2 running on http://127.0.0.1:4891")
    app.run(host="127.0.0.1", port=4891)
