const form = document.getElementById("chat-form");
const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const promptLog = document.getElementById("prompt-log");
const editorOutput = document.getElementById("editor-output");
const typingIndicator = document.getElementById("typing-indicator");
const connectionStatus = document.getElementById("connection-status");

let activeTypeJob = null;

function setConnectionStatus(message, tone = "ready") {
  connectionStatus.textContent = message;
  connectionStatus.dataset.tone = tone;
}

function appendPromptEntry(role, text) {
  const entry = document.createElement("div");
  entry.className = `prompt-entry ${role}`;

  const label = document.createElement("div");
  label.className = "label";
  label.textContent = role === "user" ? "User" : "Assistant";

  const message = document.createElement("div");
  message.className = "message";
  message.textContent = text;

  entry.appendChild(label);
  entry.appendChild(message);
  promptLog.appendChild(entry);
  promptLog.scrollTop = promptLog.scrollHeight;
}

function chunkText(text) {
  const chunks = [];
  let buffer = "";
  const maxChunk = text.length > 1500 ? 12 : 4;
  for (const char of text) {
    buffer += char;
    if (buffer.length >= maxChunk || /[\n\t]/.test(char)) {
      chunks.push(buffer);
      buffer = "";
    }
  }
  if (buffer) {
    chunks.push(buffer);
  }
  return chunks;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function typeResponse(text) {
  if (activeTypeJob) {
    activeTypeJob.cancelled = true;
  }

  const job = { cancelled: false };
  activeTypeJob = job;

  const normalized = text.replace(/\r\n/g, "\n");
  if (normalized.length > 4000) {
    editorOutput.textContent = normalized;
    typingIndicator.textContent = "Response rendered.";
    return;
  }

  editorOutput.textContent = "";
  typingIndicator.textContent = "Generating secure response...";

  const chunks = chunkText(normalized);
  for (const chunk of chunks) {
    if (job.cancelled) {
      return;
    }

    editorOutput.textContent += chunk;
    const delay = /[\n]/.test(chunk) ? 26 : 12;
    // eslint-disable-next-line no-await-in-loop
    await sleep(delay);
  }

  if (!job.cancelled) {
    typingIndicator.textContent = "Completed.";
  }
}

async function sendMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) {
    return;
  }

  appendPromptEntry("user", trimmed);
  editorOutput.textContent = "";
  typingIndicator.textContent = "Awaiting response...";
  setConnectionStatus("Contacting model", "working");

  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: trimmed }),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }

    const data = await res.json();
    const reply = data?.response ?? "";
    const safeReply = reply && String(reply).trim() ? reply : "No response received.";

    appendPromptEntry("bot", safeReply);
    await typeResponse(safeReply);
    setConnectionStatus("Ready", "ready");
  } catch (error) {
    console.error(error);
    const failureMessage = "⚠️ Network error or server issue.";
    appendPromptEntry("bot", failureMessage);
    editorOutput.textContent = failureMessage;
    typingIndicator.textContent = "Unable to retrieve response.";
    setConnectionStatus("Offline", "error");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(input.value);
  }
});

setConnectionStatus(connectionStatus.textContent || "Ready");