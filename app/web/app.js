const state = { messages: [], files: [], busy: false };
const conversation = document.querySelector("#conversation");
const welcome = document.querySelector("#welcome");
const form = document.querySelector("#chatForm");
const input = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const fileInput = document.querySelector("#fileInput");
const attachmentList = document.querySelector("#attachmentList");

function resizeInput() {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

function addMessage(role, content, temporary = false) {
  welcome?.remove();
  const item = document.createElement("article");
  item.className = `message ${role}`;
  if (temporary) item.dataset.temporary = "true";

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "CR";
    item.append(avatar);
  }

  const body = document.createElement("div");
  body.className = `message-body${temporary ? " typing" : ""}`;
  body.textContent = content;
  item.append(body);
  conversation.append(item);
  conversation.scrollTop = conversation.scrollHeight;
  return item;
}

function renderAttachments() {
  attachmentList.replaceChildren(...state.files.map((file) => {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    chip.textContent = `📎 ${file.name}`;
    return chip;
  }));
}

async function sendMessage(text) {
  if (!text.trim() || state.busy) return;
  state.busy = true;
  sendButton.disabled = true;
  addMessage("user", text.trim());
  state.messages.push({ role: "user", content: text.trim() });
  input.value = "";
  resizeInput();

  const typing = addMessage("assistant", "첨부 자료와 질문을 검토하는 중", true);
  try {
    const attachments = await Promise.all(state.files.map(fileToPayload));
    const response = await fetch("/api/v1/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: state.messages, attachments }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "응답을 받지 못했습니다.");
    typing.remove();
    addMessage("assistant", payload.message.content);
    state.messages.push(payload.message);
    state.files = [];
    fileInput.value = "";
    renderAttachments();
    saveHistory(text.trim());
  } catch (error) {
    typing.remove();
    addMessage("assistant", `연결 오류: ${error.message}\nColab 서버와 Codespaces 환경변수를 확인해 주세요.`);
  } finally {
    state.busy = false;
    sendButton.disabled = false;
    input.focus();
  }
}

function fileToPayload(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const encoded = String(reader.result).split(",", 2)[1];
      resolve({
        filename: file.name,
        mime_type: file.type || "application/octet-stream",
        data_base64: encoded,
      });
    };
    reader.onerror = () => reject(new Error(`${file.name} 파일을 읽을 수 없습니다.`));
    reader.readAsDataURL(file);
  });
}

function saveHistory(title) {
  const history = document.querySelector("#history");
  if (history.children.length) return;
  const button = document.createElement("button");
  button.className = "history-item";
  button.textContent = title;
  history.prepend(button);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});
input.addEventListener("input", resizeInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
document.querySelector("#attachButton").addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
  state.files = [...fileInput.files];
  renderAttachments();
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
});
document.querySelector("#newChat").addEventListener("click", () => window.location.reload());
document.querySelector("#menuButton").addEventListener("click", () => {
  document.querySelector("#sidebar").classList.toggle("open");
});

fetch("/api/v1/health")
  .then((response) => {
    if (!response.ok) throw new Error();
    document.querySelector(".status-dot").classList.add("online");
    document.querySelector(".status span:last-child").textContent = "Codespaces API 정상";
  })
  .catch(() => {});
