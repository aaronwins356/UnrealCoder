const API_URL = "http://127.0.0.1:1234/v1/chat/completions";
const API_HEADERS = {
  "Content-Type": "application/json",
  Authorization: "Bearer sk-fake-key",
};

const terminal = document.getElementById("terminal");
const form = document.getElementById("prompt-form");
const input = document.getElementById("prompt-input");

function createLine(role, initialText = "", withCursor = false) {
  const line = document.createElement("div");
  line.className = "line";

  const roleEl = document.createElement("span");
  roleEl.className = "role";
  roleEl.textContent = role === "user" ? ">" : "AI";

  const contentEl = document.createElement("span");
  contentEl.className = "content";

  const textEl = document.createElement("span");
  textEl.className = "content-text";
  textEl.textContent = initialText;
  contentEl.appendChild(textEl);

  if (withCursor) {
    const cursorEl = document.createElement("span");
    cursorEl.className = "cursor";
    contentEl.appendChild(cursorEl);
  }

  line.appendChild(roleEl);
  line.appendChild(contentEl);
  terminal.appendChild(line);
  terminal.scrollTop = terminal.scrollHeight;

  return { line, roleEl, contentEl, textEl, cursorEl: contentEl.querySelector(".cursor") };
}

async function streamCompletion(prompt) {
  const { textEl } = createLine("assistant", "", true);
  let accumulated = "";

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: API_HEADERS,
      body: JSON.stringify({
        model: "local-model",
        messages: [
          { role: "user", content: prompt }
        ],
        stream: true,
      }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Request failed with status ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r/g, "");

      const events = buffer.split(/\n\n/);
      buffer = events.pop() ?? "";

      for (const event of events) {
        const lines = event
          .split("\n")
          .map((line) => line.trim())
          .filter(Boolean);
        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const payload = line.replace(/^data:\s*/, "");
          if (payload === "[DONE]") {
            buffer = "";
            return;
          }
          try {
            const data = JSON.parse(payload);
            const delta = data.choices?.[0]?.delta?.content || "";
            if (delta) {
              accumulated += delta;
              textEl.textContent = accumulated;
              terminal.scrollTop = terminal.scrollHeight;
            }
          } catch (err) {
            console.error("Failed to parse payload", err, payload);
          }
        }
      }
    }
  } catch (error) {
    textEl.textContent = `Error: ${error.message}`;
    console.error(error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  createLine("user", prompt);
  input.value = "";
  await streamCompletion(prompt);
});
