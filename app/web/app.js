const state = { cases: [], activeCase: null, messages: [], files: [], busy: false, filter: "", conversationId: null, eventSource: null };
const $ = (selector) => document.querySelector(selector);
const el = (tag, className, text) => { const node = document.createElement(tag); if (className) node.className = className; if (text != null) node.textContent = text; return node; };

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `요청 실패 (${response.status})`); }
  return response.status === 204 ? null : response.json();
}

function statusLabel(status) { return { IN_PROGRESS: "진행중", COMPLETED: "완료", ON_HOLD: "보류" }[status] || status; }
function relativeTime(value) { const days = Math.floor((Date.now() - new Date(value)) / 86400000); return days <= 0 ? "방금 전" : `${days}일 전`; }
function formatSize(bytes) { return bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)}MB` : `${Math.ceil(bytes / 1024)}KB`; }
function escapeText(value) { const span = document.createElement("span"); span.textContent = value; return span.innerHTML; }

async function loadCases(selectId) {
  const query = new URLSearchParams();
  if (state.filter) query.set("status", state.filter);
  const search = $("#caseSearch").value.trim(); if (search) query.set("query", search);
  const data = await api(`/api/v1/cases?${query}`);
  state.cases = data.items;
  renderCases();
  const target = state.cases.find((item) => item.id === selectId) || state.cases[0];
  if (target && state.activeCase?.id !== target.id) await selectCase(target);
}

function renderCases() {
  const list = $("#caseList"); list.replaceChildren();
  state.cases.forEach((item) => {
    const button = el("button", `case-card${item.id === state.activeCase?.id ? " active" : ""}`);
    button.innerHTML = `<strong>${escapeText(item.title)}</strong><small>${item.id}</small><span><b>${statusLabel(item.status)}</b> · 자료 ${item.document_count}건 <em>${relativeTime(item.updated_at)}</em></span>`;
    button.addEventListener("click", () => selectCase(item)); list.append(button);
  });
  if (!state.cases.length) list.append(el("p", "empty-list", "조건에 맞는 심사건이 없습니다."));
}

async function selectCase(item) {
  state.activeCase = item; state.messages = []; state.files = []; state.conversationId = crypto.randomUUID().replaceAll("-", "");
  $("#selectorTitle").textContent = item.title; $("#selectorId").textContent = item.id; $("#caseTitle").textContent = item.title;
  $("#caseMeta").textContent = `담당자: ${item.owner_name}  |  생성일: ${new Date(item.created_at).toLocaleDateString("ko-KR")}`;
  $("#caseStatus").textContent = statusLabel(item.status); $("#caseStatus").dataset.status = item.status;
  $("#conversation").innerHTML = `<div class="empty-state compact"><div class="bot">AI</div><h2>${escapeText(item.company_name)} 심사 자료를 기반으로 질문해 주세요.</h2></div>`;
  renderCases(); renderPendingFiles(); startEventStream(); await Promise.all([loadDocuments(), loadEvents()]);
}

function addMessage(role, content, metadata = {}) {
  $(".empty-state")?.remove(); const article = el("article", `message ${role}`);
  if (role === "assistant") article.append(el("div", "message-avatar", "AI"));
  const bubble = el("div", "message-bubble"); bubble.append(el("div", "message-content", content));
  if (role === "assistant" && metadata.sources?.length) { const sources = el("div", "source-box"); sources.append(el("strong", "", "참고한 주요 자료")); metadata.sources.forEach((source) => sources.append(el("span", "", `▧ ${source}`))); bubble.append(sources); }
  article.append(bubble); $("#conversation").append(article); $("#conversation").scrollTop = $("#conversation").scrollHeight; return article;
}

function setSendButton(sending, controller = null) {
  const button = $("#sendButton"); state.currentAbortController = controller;
  button.dataset.mode = sending ? "stop" : "send"; button.classList.toggle("stop", sending);
  button.textContent = sending ? "■" : "➤ 전송"; button.setAttribute("aria-label", sending ? "답변 생성 중지" : "메시지 전송");
}

async function sendMessage(text) {
  if (!state.activeCase || !text.trim() || state.busy) return;
  const requestId = crypto.randomUUID(); const controller = new AbortController(); state.busyRequestId = requestId;
  state.busy = true; setSendButton(true, controller); addMessage("user", text.trim()); state.messages.push({ role: "user", content: text.trim() });
  $("#messageInput").value = ""; const pending = addMessage("assistant", "자료를 조회하고 있습니다…"); pending.classList.add("loading");
  const contentNode = pending.querySelector(".message-content"); let streamedAnswer = ""; let provisionalMessage = null;
  const releaseForNextQuestion = () => { if (state.busyRequestId === requestId) { state.busy = false; state.busyRequestId = null; setSendButton(false); } };
  try {
    const attachments = await Promise.all(state.files.map(fileToPayload));
    const response = await fetch("/api/v1/chat/completions/stream", { method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal, body: JSON.stringify({ messages: state.messages, attachments, conversation_id: state.conversationId, case_id: state.activeCase.id }) });
    if (!response.ok || !response.body) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || `요청 실패 (${response.status})`); }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""; let finalEvent = null;
    while (true) {
      const { value, done } = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n"); buffer = done ? "" : lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue; const event = JSON.parse(line);
        if (event.type === "meta") state.conversationId = event.conversation_id;
        if (event.type === "status" && !streamedAnswer) contentNode.textContent = event.content;
        if (event.type === "status" && event.stage === "validate" && streamedAnswer && !provisionalMessage) { provisionalMessage = { role: "assistant", content: streamedAnswer }; state.messages.push(provisionalMessage); releaseForNextQuestion(); }
        if (event.type === "token") { streamedAnswer = event.replace ? event.content : streamedAnswer + event.content; if (provisionalMessage) provisionalMessage.content = streamedAnswer; contentNode.textContent = streamedAnswer; pending.classList.remove("loading"); $("#conversation").scrollTop = $("#conversation").scrollHeight; }
        if (event.type === "done") finalEvent = event;
        if (event.type === "error") throw new Error(event.detail);
      }
      if (done) break;
    }
    if (!finalEvent) throw new Error("스트림이 완료되기 전에 연결이 종료되었습니다.");
    if (provisionalMessage) { provisionalMessage.content = finalEvent.message; contentNode.textContent = finalEvent.message; pending.classList.remove("loading"); }
    else { pending.remove(); addMessage("assistant", finalEvent.message, finalEvent.metadata); state.messages.push({ role: "assistant", content: finalEvent.message }); }
    state.files = []; renderPendingFiles(); await Promise.all([loadDocuments(), loadEvents()]);
  } catch (error) {
    if (error.name === "AbortError") { pending.classList.remove("loading"); if (streamedAnswer) { contentNode.textContent = streamedAnswer; if (!provisionalMessage) state.messages.push({ role: "assistant", content: streamedAnswer }); } else pending.remove(); }
    else if (!provisionalMessage) { pending.remove(); addMessage("assistant", `연결 오류: ${error.message}`); }
    else pending.classList.remove("loading");
  } finally { releaseForNextQuestion(); }
}
async function loadDocuments() {
  if (!state.activeCase) return; const data = await api(`/api/v1/cases/${state.activeCase.id}/documents`); const list = $("#documentList"); list.replaceChildren(); $("#documentCount").textContent = data.items.length;
  data.items.forEach((doc) => { const card = el("article", "document-card"); const ext = doc.original_name.split(".").pop().toUpperCase(); card.innerHTML = `<div class="file-icon ${ext.toLowerCase()}">${ext.slice(0,3)}</div><div class="file-info"><strong>${escapeText(doc.original_name)}</strong><small>${ext} · ${formatSize(doc.size_bytes)}</small><span>업로드: ${new Date(doc.created_at).toLocaleString("ko-KR")}</span></div><span class="doc-status ${doc.status.toLowerCase()}">${doc.status === "READY" ? "사용 가능" : doc.status}</span><button class="doc-delete" aria-label="삭제">×</button>`; card.querySelector(".doc-delete").addEventListener("click", () => removeDocument(doc.id)); list.append(card); });
  if (!data.items.length) list.append(el("p", "empty-list", "업로드된 자료가 없습니다."));
}

async function uploadDocuments(files) {
  if (!state.activeCase) return; for (const file of files) { const body = new FormData(); body.append("file", file); body.append("conversation_id", state.conversationId); await api(`/api/v1/cases/${state.activeCase.id}/documents`, { method: "POST", body }); } await loadDocuments(); await loadCases(state.activeCase.id);
}
async function removeDocument(id) { if (!confirm("이 문서를 현재 심사건에서 삭제할까요?")) return; await api(`/api/v1/cases/${state.activeCase.id}/documents/${id}`, { method: "DELETE" }); await loadDocuments(); }

async function loadEvents() {
  if (!state.activeCase) return; const data = await api(`/api/v1/cases/${state.activeCase.id}/events${state.conversationId ? `?conversation_id=${state.conversationId}` : ""}`); const timeline = $("#timeline"); timeline.replaceChildren();
  data.items.forEach((event) => { const row = el("article", "event"); row.innerHTML = `<i></i><div><strong>${escapeText(event.event_type)}</strong><small>${new Date(event.created_at).toLocaleTimeString("ko-KR")}</small><p>${escapeText(event.content || event.agent)}</p></div>`; timeline.append(row); });
  if (!data.items.length) timeline.append(el("p", "empty-list", "질문을 보내면 생성·검증 과정이 표시됩니다."));
}

function startEventStream() {
  state.eventSource?.close();
  if (!state.activeCase) return;
  const query = state.conversationId ? `?conversation_id=${state.conversationId}` : "";
  state.eventSource = new EventSource(`/api/v1/cases/${state.activeCase.id}/events/stream${query}`);
  state.eventSource.onmessage = () => loadEvents().catch(() => {});
}
function fileToPayload(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve({ filename: file.name, mime_type: file.type || "application/octet-stream", data_base64: String(reader.result).split(",", 2)[1] }); reader.onerror = reject; reader.readAsDataURL(file); }); }
function renderPendingFiles() { $("#pendingFiles").replaceChildren(...state.files.map((file) => el("span", "file-chip", `▧ ${file.name}`))); }

$("#chatForm").addEventListener("submit", (event) => { event.preventDefault(); if ($("#sendButton").dataset.mode === "stop") { state.currentAbortController?.abort(); return; } sendMessage($("#messageInput").value); });
$("#messageInput").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#chatForm").requestSubmit(); } });
$("#chatAttach").addEventListener("click", () => $("#chatFile").click());
$("#chatFile").addEventListener("change", () => { state.files = [...$("#chatFile").files]; renderPendingFiles(); });
$("#documentInput").addEventListener("change", () => uploadDocuments([...$("#documentInput").files]).catch((error) => alert(error.message)));
$("#dropzone").addEventListener("dragover", (event) => event.preventDefault()); $("#dropzone").addEventListener("drop", (event) => { event.preventDefault(); uploadDocuments([...event.dataTransfer.files]).catch((error) => alert(error.message)); });
$("#newCase").addEventListener("click", () => $("#caseDialog").showModal());
$("#caseForm").addEventListener("submit", async (event) => { if (event.submitter?.value === "cancel") return; event.preventDefault(); const data = Object.fromEntries(new FormData(event.currentTarget)); try { const item = await api("/api/v1/cases", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }); $("#caseDialog").close(); event.currentTarget.reset(); await loadCases(item.id); } catch (error) { alert(error.message); } });
$("#caseSearch").addEventListener("input", () => loadCases(state.activeCase?.id));
$("#caseFilters").addEventListener("click", (event) => { const button = event.target.closest("button"); if (!button) return; $("#caseFilters .active").classList.remove("active"); button.classList.add("active"); state.filter = button.dataset.status; loadCases(); });
$("#traceToggle").addEventListener("click", () => { $("#tracePanel").classList.toggle("hidden"); $("#contentGrid").classList.toggle("trace-open", !$("#tracePanel").classList.contains("hidden")); loadEvents(); });
$("#documentToggle").addEventListener("click", () => $("#documentsPanel").classList.toggle("hidden"));
$("[data-close=trace]").addEventListener("click", () => { $("#tracePanel").classList.add("hidden"); $("#contentGrid").classList.remove("trace-open"); });
$("[data-close=documents]").addEventListener("click", () => $("#documentsPanel").classList.add("hidden"));
loadCases().catch((error) => addMessage("assistant", `초기화 오류: ${error.message}`));