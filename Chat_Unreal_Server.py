# Chat_Unreal Server with Tor, Ollama & Memory
import os, json, requests, subprocess, threading, time
from flask import Flask, request, jsonify, send_from_directory
from bs4 import BeautifulSoup

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
MEMORY_PATH = os.path.join(BASE_DIR, "chat_memory.json")
LOG_PATH = os.path.join(BASE_DIR, "chat_unreal.log")

# Load config
with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
    CFG = json.load(f)

# Persistent memory
if not os.path.exists(MEMORY_PATH):
    with open(MEMORY_PATH, "w", encoding="utf-8-sig") as f:
        json.dump({"history": []}, f)

def log(msg):
    with open(LOG_PATH, "a", encoding="utf-8-sig") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def load_memory():
    with open(MEMORY_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_memory(mem):
    with open(MEMORY_PATH, "w", encoding="utf-8-sig") as f:
        json.dump(mem, f, indent=2)

# Tor launcher
def launch_tor():
    if not CFG.get("use_tor"): return
    tor_path = CFG.get("tor_path")
    if not os.path.exists(tor_path):
        log("Tor path invalid.")
        return
    def _run_tor():
        log("Starting Tor...")
        subprocess.run([tor_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=_run_tor, daemon=True).start()

launch_tor()
time.sleep(5)

def tor_request(url):
    proxies = {
        "http": "socks5h://127.0.0.1:9050",
        "https": "socks5h://127.0.0.1:9050"
    }
    try:
        r = requests.get(url, proxies=proxies, timeout=20)
        return r.text
    except:
        log("Tor request failed, fallback to clear web.")
        return requests.get(url, timeout=15).text

def search_web(query):
    q = query.replace(" ", "+")
    html = tor_request(f"https://duckduckgo.com/html/?q={q}")
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for a in soup.select("a.result__a")[:5]:
        results.append({"title": a.text, "url": a["href"]})
    return results

@app.route("/")
def serve_ui():
    return send_from_directory(BASE_DIR, "Chat_Unreal.html")

@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"response": "No message provided."})

    mem = load_memory()
    mem["history"].append({"role": "user", "content": user_msg})

    # Web research if user requests it
    if any(x in user_msg.lower() for x in ["search", "find", "lookup", "web"]):
        results = search_web(user_msg)
        context = " ".join([r["title"] for r in results])
    else:
        context = ""

    payload = {
        "model": CFG["model"],
        "messages": [{"role": "system", "content": "You are Chat Unreal, a factual, step-by-step instructional AI."}]
                    + mem["history"][-8:]
                    + [{"role": "user", "content": context + user_msg}],
        "stream": False,
    }

    try:
        r = requests.post("http://localhost:11434/api/chat", json=payload, timeout=60)
        response_json = r.json()
        reply = response_json.get("message", {}).get("content", "No response.")
    except Exception as e:
        reply = f"Error: {e}"

    mem["history"].append({"role": "assistant", "content": reply})
    save_memory(mem)
    log(f"User: {user_msg}\nAI: {reply}\n")

    return jsonify({"response": reply})

if __name__ == "__main__":
    print("🔥 Chat_Unreal_V2 running on http://127.0.0.1:4891")
    app.run(host="127.0.0.1", port=4891)

