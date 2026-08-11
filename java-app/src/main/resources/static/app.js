const TOKEN_STORAGE_KEY = "livestock_enterprise_token_pair";
const ACTIVE_CONVERSATION_KEY = "livestock_enterprise_active_conversation";
const TERMINAL_TASK_STATUSES = new Set(["SUCCEEDED", "FAILED", "TIMED_OUT", "CANCELLED"]);

const state = {
  tokens: readTokens(),
  user: null,
  conversations: [],
  activeConversation: null,
  lastResponse: null,
  submitting: false,
  refreshPromise: null,
};

const $ = (selector) => document.querySelector(selector);

class ApiError extends Error {
  constructor(message, code, status, payload) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.payload = payload;
  }
}

function uniqueId(prefix) {
  const value = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${value}`;
}

function readTokens() {
  try {
    const value = sessionStorage.getItem(TOKEN_STORAGE_KEY);
    return value ? JSON.parse(value) : null;
  } catch {
    return null;
  }
}

function saveTokens(tokens) {
  state.tokens = tokens;
  state.user = tokens?.user || null;
  try {
    if (tokens) sessionStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens));
    else sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // The application still works in memory when browser storage is unavailable.
  }
}

function clearSession() {
  saveTokens(null);
  state.conversations = [];
  state.activeConversation = null;
  try {
    sessionStorage.removeItem(ACTIVE_CONVERSATION_KEY);
  } catch {
    // no-op
  }
}

async function refreshTokens() {
  const refreshToken = state.tokens?.refreshToken;
  if (!refreshToken) throw new ApiError("登录已失效，请重新登录。", "AUTHENTICATION_REQUIRED", 401);
  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": uniqueId("web-refresh"),
    },
    body: JSON.stringify({ refreshToken }),
  });
  const payload = await readJson(response);
  if (!response.ok) {
    clearSession();
    throw apiError(response, payload);
  }
  saveTokens(payload.data);
}

async function ensureFreshTokens() {
  if (!state.refreshPromise) {
    state.refreshPromise = refreshTokens().finally(() => { state.refreshPromise = null; });
  }
  return state.refreshPromise;
}

async function api(path, options = {}, allowRefresh = true) {
  const headers = new Headers(options.headers || {});
  const requestAccessToken = state.tokens?.accessToken;
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (requestAccessToken) headers.set("Authorization", `Bearer ${requestAccessToken}`);
  if (!headers.has("X-Request-ID")) headers.set("X-Request-ID", uniqueId("web"));

  const response = await fetch(path, { ...options, headers });
  if (response.status === 401 && allowRefresh && state.tokens?.refreshToken && !path.includes("/auth/")) {
    if (state.tokens?.accessToken === requestAccessToken) await ensureFreshTokens();
    return api(path, options, false);
  }
  const payload = response.status === 204 ? null : await readJson(response);
  if (!response.ok) throw apiError(response, payload);
  if (payload) renderDetails(payload);
  return { response, payload };
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function apiError(response, payload) {
  const code = payload?.error?.code || "REQUEST_FAILED";
  const message = payload?.error?.message || `请求失败（HTTP ${response.status}）`;
  return new ApiError(message, code, response.status, payload);
}

function showLogin(message = "") {
  $("#app-shell").hidden = true;
  $("#login-shell").hidden = false;
  const error = $("#login-error");
  error.textContent = message;
  error.hidden = !message;
  $("#password").value = "";
  $("#username").focus();
}

function showApplication() {
  $("#login-shell").hidden = true;
  $("#app-shell").hidden = false;
  state.user = state.tokens?.user || state.user;
  $("#current-username").textContent = state.user?.username || "用户";
  $("#current-roles").textContent = Array.isArray(state.user?.roles)
    ? state.user.roles.join(" · ")
    : "USER";
  $(".avatar").textContent = (state.user?.username || "U").slice(0, 1).toUpperCase();
}

async function handleLogin(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const submit = form.querySelector("button[type='submit']");
  submit.disabled = true;
  $("#login-error").hidden = true;
  try {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Request-ID": uniqueId("web-login"),
      },
      body: JSON.stringify({
        username: String(data.get("username") || "").trim(),
        password: String(data.get("password") || ""),
      }),
    });
    const payload = await readJson(response);
    if (!response.ok) throw apiError(response, payload);
    saveTokens(payload.data);
    form.reset();
    showApplication();
    await bootstrapWorkspace();
  } catch (error) {
    showLogin(userMessage(error));
  } finally {
    submit.disabled = false;
  }
}

async function handleLogout() {
  $("#logout-button").disabled = true;
  try {
    if (state.tokens?.accessToken) await api("/api/v1/auth/logout", { method: "POST" }, false);
  } catch {
    // Local credentials must be cleared even when the server is unavailable.
  } finally {
    clearSession();
    $("#logout-button").disabled = false;
    showLogin();
  }
}

async function bootstrapWorkspace() {
  renderWelcome();
  const [, conversationsResult] = await Promise.allSettled([loadSystemStatus(), loadConversations()]);
  if (conversationsResult.status === "rejected") throw conversationsResult.reason;
  const storedId = storedConversationId();
  const target = state.conversations.find((item) => item.id === storedId) || state.conversations[0];
  if (target) await openConversation(target.id);
}

async function loadSystemStatus() {
  try {
    const { payload } = await api("/api/v1/system/status");
    const dependencies = payload?.data?.dependencies || {};
    setStatus($("#java-status"), "Java", dependencies.mysql?.status === "UP" && dependencies.redis?.status === "UP");
    setStatus($("#python-status"), "Python AI", dependencies.pythonAi?.status === "UP");
  } catch {
    setStatus($("#java-status"), "Java", false);
    setStatus($("#python-status"), "Python AI", false);
  }
}

function setStatus(node, label, isUp) {
  node.classList.toggle("is-up", isUp);
  node.classList.toggle("is-down", !isUp);
  node.innerHTML = `<i></i>${escapeHtml(label)} ${isUp ? "UP" : "DOWN"}`;
}

async function loadConversations() {
  const { payload } = await api("/api/v1/conversations?scope=own&page=0&size=100");
  state.conversations = payload?.data?.items || [];
  renderConversationList();
}

function renderConversationList() {
  const query = $("#conversation-search").value.trim().toLocaleLowerCase("zh-CN");
  const items = state.conversations.filter((item) => !query || item.title.toLocaleLowerCase("zh-CN").includes(query));
  $("#conversation-count").textContent = String(state.conversations.length);
  if (!items.length) {
    $("#conversation-list").innerHTML = `<p class="empty-list">${query ? "没有匹配的会话" : "发送第一条消息后，会话会显示在这里。"}</p>`;
    return;
  }
  $("#conversation-list").innerHTML = items.map((item) => `
    <article class="conversation-item${item.id === state.activeConversation?.id ? " is-active" : ""}" data-id="${escapeHtml(item.id)}">
      <button class="conversation-open" type="button" data-action="open">
        <strong>${escapeHtml(item.title)}</strong>
        <time>${escapeHtml(formatTime(item.lastMessageAt || item.updatedAt))}</time>
      </button>
      <div class="conversation-actions">
        <button type="button" data-action="rename" title="重命名" aria-label="重命名 ${escapeHtml(item.title)}">✎</button>
        <button type="button" data-action="delete" title="删除" aria-label="删除 ${escapeHtml(item.title)}">×</button>
      </div>
    </article>
  `).join("");
}

function startNewConversation() {
  state.activeConversation = null;
  storeConversationId(null);
  $("#active-title").textContent = "新对话";
  renderConversationList();
  renderWelcome();
  renderDetails({ data: { state: "READY", instruction: "发送问题后由 Java 创建业务会话并调用 Python AI 服务。" } });
  $("#message-input").focus();
}

async function createConversation(firstMessage) {
  const title = firstMessage.trim().replace(/\s+/g, " ").slice(0, 48) || "新对话";
  const { payload } = await api("/api/v1/conversations", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
  state.activeConversation = payload.data;
  storeConversationId(payload.data.id);
  await loadConversations();
  return payload.data;
}

async function openConversation(id) {
  setComposerDisabled(true);
  try {
    const { payload } = await api(`/api/v1/conversations/${encodeURIComponent(id)}`);
    state.activeConversation = payload.data.conversation;
    storeConversationId(id);
    $("#active-title").textContent = state.activeConversation.title;
    renderConversationList();
    renderMessages(payload.data.messages || []);
  } catch (error) {
    appendError(userMessage(error));
  } finally {
    if (!state.submitting) setComposerDisabled(false);
  }
}

async function renameConversation(conversation) {
  const title = prompt("新的会话名称", conversation.title)?.trim();
  if (!title || title === conversation.title) return;
  try {
    await api(`/api/v1/conversations/${encodeURIComponent(conversation.id)}`, {
      method: "PATCH",
      body: JSON.stringify({ title, status: conversation.status, version: conversation.version }),
    });
    await loadConversations();
    if (state.activeConversation?.id === conversation.id) await openConversation(conversation.id);
  } catch (error) {
    alert(userMessage(error));
  }
}

async function deleteConversation(conversation) {
  if (!confirm(`确定删除“${conversation.title}”吗？此操作不可撤销。`)) return;
  try {
    await api(`/api/v1/conversations/${encodeURIComponent(conversation.id)}?version=${conversation.version}`, {
      method: "DELETE",
    });
    if (state.activeConversation?.id === conversation.id) startNewConversation();
    await loadConversations();
  } catch (error) {
    alert(userMessage(error));
  }
}

async function handleConversationAction(event) {
  const item = event.target.closest(".conversation-item");
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!item || !action) return;
  const conversation = state.conversations.find((entry) => entry.id === item.dataset.id);
  if (!conversation) return;
  if (action === "open") await openConversation(conversation.id);
  if (action === "rename") await renameConversation(conversation);
  if (action === "delete") await deleteConversation(conversation);
}

async function submitMessage(event) {
  event.preventDefault();
  if (state.submitting) return;
  const form = event.currentTarget;
  const content = String(new FormData(form).get("content") || "").trim();
  if (!content) return;
  state.submitting = true;
  setComposerDisabled(true);

  try {
    const conversation = state.activeConversation || await createConversation(content);
    appendTransientMessage("USER", content);
    appendPendingMessage();
    const operationId = uniqueId("web-operation");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 65000);
    let result;
    try {
      result = await api(`/api/v1/conversations/${encodeURIComponent(conversation.id)}/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": operationId },
        body: JSON.stringify({ content, contextVersion: conversation.contextVersion }),
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    const task = result.payload?.data?.task;
    if (task && !TERMINAL_TASK_STATUSES.has(task.status)) await pollTask(task.id);
    if (task?.status === "FAILED" || task?.status === "CANCELLED") {
      throw new ApiError(`AI 任务未完成：${task.errorCode || task.status}`, task.errorCode || task.status, 503, result.payload);
    }
    form.reset();
    await openConversation(conversation.id);
    await loadConversations();
  } catch (error) {
    removePendingMessage();
    const message = error?.name === "AbortError"
      ? "AI 请求超过 65 秒，请稍后重新打开会话查看任务结果。"
      : userMessage(error);
    if (state.activeConversation?.id) {
      try { await openConversation(state.activeConversation.id); } catch { /* keep visible error */ }
    }
    appendError(message);
  } finally {
    state.submitting = false;
    setComposerDisabled(false);
    $("#message-input").focus();
  }
}

async function pollTask(taskId) {
  const deadline = Date.now() + 70000;
  while (Date.now() < deadline) {
    await wait(1000);
    const { payload } = await api(`/api/v1/tasks/${encodeURIComponent(taskId)}`);
    const task = payload.data;
    if (TERMINAL_TASK_STATUSES.has(task.status)) {
      if (task.status !== "SUCCEEDED") {
        throw new ApiError(`AI 任务未完成：${task.errorCode || task.status}`, task.errorCode || task.status, 503, payload);
      }
      return task;
    }
  }
  throw new ApiError("任务仍在处理中，请稍后重新打开会话。", "TASK_TIMEOUT", 504);
}

async function handleDocumentUpload(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const file = new FormData(form).get("file");
  if (!(file instanceof File) || !file.size) return;
  const submit = $("#submit-upload");
  const status = $("#upload-status");
  submit.disabled = true;
  status.className = "upload-status is-running";
  status.textContent = "Java 正在校验文件并创建 DOCUMENT_INDEX 任务……";
  try {
    const body = new FormData();
    body.append("file", file);
    const result = await api("/api/v1/documents", {
      method: "POST",
      headers: { "Idempotency-Key": uniqueId("web-document") },
      body,
    });
    const document = result.payload.data.document;
    let task = result.payload.data.task;
    status.textContent = `任务 ${task.id} 已创建，正在等待 Python 执行……`;
    if (!TERMINAL_TASK_STATUSES.has(task.status)) task = await pollTask(task.id);
    const latest = await api(`/api/v1/documents/${encodeURIComponent(document.id)}`);
    const view = latest.payload.data;
    const real = view.executionMode === "REAL";
    status.className = `upload-status ${task.status === "SUCCEEDED" ? "is-success" : "is-error"}`;
    status.textContent = task.status === "SUCCEEDED"
      ? `${view.fileName} 已完成：${real ? "真实索引已写入" : "FAKE 模式交付校验通过"}（${view.status}）`
      : `索引任务未完成：${task.errorCode || task.status}`;
    renderDetails(latest.payload);
    form.reset();
  } catch (error) {
    status.className = "upload-status is-error";
    status.textContent = userMessage(error);
  } finally {
    submit.disabled = false;
  }
}

function optionalMeasurement(formData, name) {
  const raw = String(formData.get(name) || "").trim();
  return raw === "" ? null : Number(raw);
}

function renderMeasurementResult(analysis) {
  const result = analysis.result;
  $("#measurement-outcome").textContent = analysis.outcome;
  $("#measurement-animal").textContent = `${analysis.animalCode}（ID ${analysis.animalId}）`;
  $("#measurement-operation-id").textContent = analysis.operationId;
  $("#measurement-summary").textContent = result.summary;
  $("#measurement-abnormal-items").textContent = result.abnormalItems.join("；") || "无";
  $("#measurement-recommendation").textContent = result.recommendation;
  $("#measurement-report").textContent = result.report;
  const evidence = $("#measurement-evidence");
  const items = result.evidence.length ? result.evidence : ["无"];
  evidence.replaceChildren(...items.map((item) => {
    const node = document.createElement("li");
    node.textContent = item;
    return node;
  }));
  $("#measurement-result").hidden = false;
}

async function handleMeasurementAnalysis(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = new FormData(form);
  const current = Object.fromEntries([
    "bodyHeightCm",
    "bodyLengthCm",
    "chestGirthCm",
    "chestDepthCm",
    "chestWidthCm",
    "weightKg",
  ].map((name) => [name, optionalMeasurement(data, name)]));
  const status = $("#measurement-status");
  const resultView = $("#measurement-result");
  if (!Object.values(current).some((value) => value !== null)) {
    status.className = "upload-status is-error";
    status.textContent = "请至少填写一项本次测量值。";
    return;
  }

  const submit = $("#submit-measurement");
  const confidence = optionalMeasurement(data, "confidence");
  const request = {
    animalId: Number(data.get("animalId")),
    current,
    ...(confidence === null ? {} : { confidence }),
  };
  submit.disabled = true;
  resultView.hidden = true;
  status.className = "upload-status is-running";
  status.textContent = "Java 正在加载授权快照并调用 Python AI 服务……";
  try {
    const { payload } = await api("/api/v1/measurements/analyze", {
      method: "POST",
      headers: { "Idempotency-Key": uniqueId("web-measurement") },
      body: JSON.stringify(request),
    });
    const analysis = payload.data;
    const analyzed = analysis.outcome === "ANALYZED";
    const controlledOutcome = new Set(["LOW_CONFIDENCE", "INSUFFICIENT_DATA"]).has(analysis.outcome);
    status.className = `upload-status ${analyzed ? "is-success" : controlledOutcome ? "is-warning" : "is-error"}`;
    status.textContent = `${analysis.animalCode} 分析完成：${analysis.outcome}`;
    renderMeasurementResult(analysis);
  } catch (error) {
    status.className = "upload-status is-error";
    status.textContent = userMessage(error);
  } finally {
    submit.disabled = false;
  }
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function renderWelcome() {
  const template = $("#welcome-template");
  const list = $("#message-list");
  list.innerHTML = "";
  list.appendChild(template.content.cloneNode(true));
}

function renderMessages(messages) {
  const list = $("#message-list");
  if (!messages.length) {
    renderWelcome();
    return;
  }
  list.innerHTML = messages.map(renderMessage).join("");
  list.scrollTop = list.scrollHeight;
}

function renderMessage(message) {
  const role = message.role === "USER" ? "user" : "assistant";
  const metadata = message.metadata || {};
  const badges = [];
  if (message.intent) badges.push(`<span class="message-badge">${escapeHtml(message.intent)}</span>`);
  if (message.riskLevel) badges.push(`<span class="message-badge${["HIGH", "CRITICAL"].includes(message.riskLevel) ? " danger" : ""}">风险 ${escapeHtml(message.riskLevel)}</span>`);
  if (message.evidenceStatus) badges.push(`<span class="message-badge${["LOW_CONFIDENCE", "EMPTY", "UNAVAILABLE"].includes(message.evidenceStatus) ? " warning" : ""}">证据 ${escapeHtml(message.evidenceStatus)}</span>`);
  if (metadata.outcome) badges.push(`<span class="message-badge">${escapeHtml(metadata.outcome)}</span>`);
  return `
    <article class="message ${role}">
      <div class="message-avatar" aria-hidden="true">${role === "user" ? "U" : "R"}</div>
      <div class="message-body">
        <div class="message-meta"><span>${role === "user" ? "你" : "AI 助手"}</span>${badges.join("")}</div>
        <p>${escapeHtml(message.content || "")}</p>
        ${role === "assistant" ? renderAssistantMetadata(metadata) : ""}
      </div>
    </article>
  `;
}

function renderAssistantMetadata(metadata) {
  const sources = Array.isArray(metadata.sources) ? metadata.sources : [];
  const tools = Array.isArray(metadata.toolsUsed) ? metadata.toolsUsed : [];
  const followUps = Array.isArray(metadata.followUpQuestions) ? metadata.followUpQuestions : [];
  const sourceHtml = sources.length ? `
    <section class="message-extra"><h3>引用来源</h3><ol>${sources.map((source) => `
      <li>${escapeHtml(source.title || source.sourceUri || "未命名来源")}${source.page ? ` · P${escapeHtml(source.page)}` : ""}${source.score !== undefined ? ` · ${Number(source.score).toFixed(3)}` : ""}</li>
    `).join("")}</ol></section>` : "";
  const toolHtml = tools.length ? `
    <section class="message-extra"><h3>工具调用</h3><div class="tool-list">${tools.map((tool) => `<span>${escapeHtml(tool)}</span>`).join("")}</div></section>` : "";
  const followUpHtml = followUps.length ? `
    <section class="message-extra"><h3>建议追问</h3><ul>${followUps.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></section>` : "";
  const safetyHtml = metadata.safety?.decision ? `
    <section class="message-extra"><h3>安全决策</h3><div class="tool-list"><span>${escapeHtml(metadata.safety.decision)}</span>${metadata.safety.reasonCode ? `<span>${escapeHtml(metadata.safety.reasonCode)}</span>` : ""}</div></section>` : "";
  return `${sourceHtml}${toolHtml}${followUpHtml}${safetyHtml}`;
}

function appendTransientMessage(role, content) {
  const list = $("#message-list");
  if (list.querySelector(".welcome-card")) list.innerHTML = "";
  list.insertAdjacentHTML("beforeend", renderMessage({ role, content, metadata: {} }));
  list.scrollTop = list.scrollHeight;
}

function appendPendingMessage() {
  removePendingMessage();
  $("#message-list").insertAdjacentHTML("beforeend", `
    <article class="message assistant pending-message" id="pending-message">
      <div class="message-avatar" aria-hidden="true">R</div>
      <div class="message-body">
        <div class="message-meta">Java 正在编排 Python AI 服务</div>
        <span class="typing-dots" aria-label="处理中"><i></i><i></i><i></i></span>
      </div>
    </article>
  `);
  $("#message-list").scrollTop = $("#message-list").scrollHeight;
}

function removePendingMessage() {
  $("#pending-message")?.remove();
}

function appendError(message) {
  removePendingMessage();
  const list = $("#message-list");
  if (list.querySelector(".welcome-card")) list.innerHTML = "";
  list.insertAdjacentHTML("beforeend", `
    <article class="message assistant">
      <div class="message-avatar" aria-hidden="true">!</div>
      <div class="message-body"><div class="message-meta">请求未完成</div><p class="error-banner">${escapeHtml(message)}</p></div>
    </article>
  `);
  list.scrollTop = list.scrollHeight;
}

function renderDetails(payload) {
  state.lastResponse = payload;
  const data = payload?.data || {};
  const task = data.task || (data.status && data.operationId ? data : null);
  const assistant = data.assistantMessage || null;
  const measurement = data.outcome && data.result && data.animalId ? data : null;
  const rows = [
    ["Request ID", payload?.requestId || "-"],
    ["Conversation", state.activeConversation?.id || "new"],
    ["Context Version", state.activeConversation?.contextVersion ?? "-"],
    ["Task", task ? `${task.id} / ${task.status}` : "-"],
    ["Operation", measurement?.operationId || "-"],
    ["Outcome", measurement?.outcome || assistant?.metadata?.outcome || "-"],
    ["Evidence", measurement ? `${measurement.result.evidence.length} items` : assistant?.evidenceStatus || "-"],
  ];
  $("#detail-summary").innerHTML = rows.map(([label, value]) => `
    <div class="detail-row"><strong>${escapeHtml(label)}</strong><span>${escapeHtml(value)}</span></div>
  `).join("");
  $("#detail-json").textContent = JSON.stringify(payload || {}, null, 2);
}

function setComposerDisabled(disabled) {
  $("#message-form").querySelectorAll("textarea, button").forEach((node) => { node.disabled = disabled; });
}

function storedConversationId() {
  try {
    return sessionStorage.getItem(ACTIVE_CONVERSATION_KEY);
  } catch {
    return null;
  }
}

function storeConversationId(id) {
  try {
    if (id) sessionStorage.setItem(ACTIVE_CONVERSATION_KEY, id);
    else sessionStorage.removeItem(ACTIVE_CONVERSATION_KEY);
  } catch {
    // no-op
  }
}

function formatTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function userMessage(error) {
  if (error?.code === "CONTEXT_VERSION_MISMATCH") return "会话状态已更新，请重新发送这条消息。";
  if (error?.code === "AI_SERVICE_UNAVAILABLE") return "AI 服务暂时不可用，任务状态已保留，请稍后重试。";
  if (error?.code === "ACCESS_DENIED") return "当前账号没有执行此操作的权限。";
  if (error?.code === "ANIMAL_NOT_FOUND") return "动物不存在，或当前账号无权访问。";
  if (error?.code === "ANIMAL_PROFILE_INCOMPLETE") return "动物档案不完整，暂时无法进行 AI 分析。";
  if (error?.code === "AI_BUSY") return "AI 服务繁忙，请稍后重试。";
  if (error?.code === "AI_TIMEOUT") return "AI 分析超时，请稍后重试。";
  if (error?.code === "AI_PROTOCOL_ERROR") return "AI 服务返回了无法验证的结果。";
  if (error?.code === "MEASUREMENT_REQUEST_REJECTED") return "体尺分析请求被 AI 服务拒绝。";
  if (error instanceof ApiError) return `${error.message}（${error.code}）`;
  return error?.message || String(error || "未知错误");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

$("#login-form").addEventListener("submit", handleLogin);
$("#logout-button").addEventListener("click", handleLogout);
$("#new-conversation").addEventListener("click", startNewConversation);
$("#conversation-search").addEventListener("input", renderConversationList);
$("#conversation-list").addEventListener("click", handleConversationAction);
$("#message-form").addEventListener("submit", submitMessage);
$("#open-upload").addEventListener("click", () => $("#upload-dialog").showModal());
$("#close-upload").addEventListener("click", () => $("#upload-dialog").close());
$("#upload-form").addEventListener("submit", handleDocumentUpload);
$("#open-measurement").addEventListener("click", () => $("#measurement-dialog").showModal());
$("#close-measurement").addEventListener("click", () => $("#measurement-dialog").close());
$("#measurement-form").addEventListener("submit", handleMeasurementAnalysis);
$("#message-input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    event.currentTarget.form.requestSubmit();
  }
});
document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    $("#message-input").value = button.dataset.prompt || "";
    $("#message-input").focus();
  });
});

if (state.tokens?.accessToken && state.tokens?.refreshToken) {
  showApplication();
  bootstrapWorkspace().catch((error) => {
    if (error?.status === 401) {
      clearSession();
      showLogin("登录已失效，请重新登录。");
    } else {
      appendError(userMessage(error));
    }
  });
} else {
  clearSession();
  showLogin();
}
