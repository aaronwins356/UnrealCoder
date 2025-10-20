const input = document.getElementById("user-input");
const sendBtn = document.getElementById("send-btn");
const chatBox = document.getElementById("chat-box");

function addMessage(role, text) {
  const msgWrap = document.createElement("div");
  msgWrap.classList.add("chat-msg", role);

  const bubble = document.createElement("div");
  bubble.classList.add("bubble");
  bubble.innerHTML = text
    .replace(/\n/g, "<br>")
    .replace(/(\d+\.)/g, "<br>$1");

  msgWrap.appendChild(bubble);
  chatBox.appendChild(msgWrap);
  chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessage() {
  const message = input.value.trim();
  if (!message) return;

  addMessage("user", message);
  input.value = "";
  input.disabled = true;
  sendBtn.disabled = true;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    const data = await res.json();
    addMessage("bot", data.response);
  } catch (error) {
    addMessage("bot", "⚠️ Network error or server issue.");
  } finally {
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
  }
}

sendBtn.onclick = sendMessage;
input.addEventListener("keypress", (e) => {
  if (e.key === "Enter") sendMessage();
});