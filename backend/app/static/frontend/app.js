const CHAT_SESSION_STORAGE_KEY = "livestock_agentic_rag_chat_session_id";
const CLIENT_ID_STORAGE_KEY = "livestock_agentic_rag_client_id";

const state = {
  lastResponse: null,
  ragStatus: null,
  pendingAssistantNode: null,
  chatSessionId: getOrCreateChatSessionId(),
  conversations: [],
  conversationTotal: 0,
  conversationPageSize: 50,
  conversationSearch: "",
  openConversationMenu: null,
  clientId: getOrCreateClientId(),
  activeChatRequest: null,
  pendingAssistantSessionId: null,
  conversationLoadToken: 0,
  chatRequestToken: 0,
  conversationListToken: 0,
};

const labels = {
  intents: {
    assistant_intro: "助手介绍",
    general_qa: "知识问答",
    disease_consultation: "疾病问诊",
    measurement_analysis: "体尺分析",
    out_of_scope: "普通对话",
  },
  risks: {
    low: "低风险",
    medium: "中风险",
    high: "高风险",
    emergency: "紧急",
  },
};

function setActiveView(viewName) {
  document.querySelectorAll(".tab").forEach((tab) => {
    const isActive = tab.dataset.view === viewName;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `${viewName}-view`);
  });
}

function renderDebugPanel(payload) {
  state.lastResponse = payload;
  const summary = buildDebugSummary(payload || {});
  renderDebugSummary(summary);
  document.querySelector("#debug-json").textContent = JSON.stringify({ summary, raw: payload || {} }, null, 2);
}

function buildDebugSummary(payload) {
  const data = payload.data || {};
  const v3DebugSummary = data.v3_debug_summary || buildV3DebugSummary(data);
  const ragStatus = data.v3_debug?.rag_status || v3DebugSummary.rag_status || state.ragStatus || {};
  return {
    request_id: payload.request_id || data.request_id || null,
    rag_mode: data.rag_mode_effective || data.rag_mode || ragStatus.rag_mode_effective || ragStatus.rag_mode || null,
    rag_status: normalizeRagStatus(ragStatus),
    agent_path: data.agent_path || nodesFromTrace(data.agent_trace) || data.tools_used || [],
    safety: data.safety_result || data.safety || "not_available",
    verifier: data.verification_result || data.verifier_result || "not_available",
    v3_debug_summary: v3DebugSummary,
  };
}

function buildV3DebugSummary(data) {
  const flags = data.v3_debug?.flags || {};
  return {
    flags,
    route: data.route || { status: "not_available" },
    safety: data.safety_result || data.safety || { status: "not_available" },
    memory: {
      write_enabled: Boolean(flags.memory_write_enabled),
      read_enabled: Boolean(flags.memory_read_enabled),
    },
    rag_status: data.v3_debug?.rag_status || {},
  };
}

function renderDebugSummary(summary) {
  const container = document.querySelector("#debug-summary");
  if (!container) return;
  const v3 = summary.v3_debug_summary || {};
  const flags = v3.flags || {};
  const route = v3.route || {};
  const safety = v3.safety || {};
  const memory = v3.memory || {};
  container.innerHTML = `
    <div><strong>Flags</strong><span>${escapeHtml(flags.v3_enabled ? "v3:on" : "v3:off")}</span></div>
    <div><strong>Route</strong><span>${escapeHtml(route.route_mode || route.status || "not_available")}</span></div>
    <div><strong>Safety</strong><span>${escapeHtml(String(safety.passed ?? safety.status ?? "not_available"))}</span></div>
    <div><strong>Memory</strong><span>${escapeHtml(memory.write_enabled ? "write:on" : "write:off")}</span></div>
    ${renderRagStatus(summary.rag_status)}
  `;
  updateRagStatusUi(summary.rag_status);
}

function normalizeRagStatus(ragStatus) {
  return {
    rag_mode: ragStatus.rag_mode_effective || ragStatus.rag_mode || "unknown",
    collection: ragStatus.collection || ragStatus.default_collection || "unknown",
    batch_id: ragStatus.batch_id || null,
    quality_gate_status: ragStatus.quality_gate_status || "not_configured",
  };
}

function renderRagStatus(ragStatus) {
  const status = normalizeRagStatus(ragStatus || {});
  const parts = [
    status.rag_mode,
    status.collection,
    status.batch_id || "no_batch",
    status.quality_gate_status,
  ];
  return `<div class="rag-status"><strong>RAG</strong><span>${escapeHtml(parts.join(" / "))}</span></div>`;
}

function updateRagStatusUi(ragStatus) {
  const status = normalizeRagStatus(ragStatus || {});
  const text = `${status.rag_mode} / ${status.collection}`;
  const sidebar = document.querySelector("#rag-sidebar-status");
  const pill = document.querySelector("#mode-pill");
  if (sidebar) sidebar.textContent = text;
  if (pill) pill.textContent = `RAG: ${text}`;
}

function nodesFromTrace(agentTrace) {
  if (!Array.isArray(agentTrace)) return null;
  return agentTrace.map((item) => item.node).filter(Boolean);
}

async function loadRagStatus() {
  try {
    const response = await fetch("/api/rag/status");
    const payload = await response.json();
    state.ragStatus = payload.data || null;
    renderDebugPanel(state.lastResponse || payload);
  } catch {
    renderDebugPanel(state.lastResponse || {});
  }
}

async function submitChat(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const query = new FormData(form).get("query")?.toString().trim();
  if (!query) return;

  const requestSessionId = form.dataset.sessionId || state.chatSessionId || getOrCreateChatSessionId();
  appendMessage("user", query, "你");
  state.pendingAssistantNode = appendMessage("assistant", "正在理解问题并生成回复...", "处理中", { loading: true });
  state.pendingAssistantSessionId = requestSessionId;
  setFormDisabled(form, true);
  const controller = new AbortController();
  const requestToken = ++state.chatRequestToken;
  state.activeChatRequest = { sessionId: requestSessionId, controller, requestToken };
  const timeoutId = window.setTimeout(() => controller.abort(), 60000);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        session_id: requestSessionId,
        user_id: state.clientId,
      }),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok || payload.code !== 0) {
      throw new Error(payload.message || "请求失败，请检查输入后重试。");
    }
    if (state.chatRequestToken !== requestToken || state.chatSessionId !== requestSessionId) return;
    renderChat(payload.data || {});
    renderDebugPanel(payload);
    form.reset();
    await loadConversationList(state.conversationSearch);
  } catch (error) {
    if (state.chatRequestToken !== requestToken || state.chatSessionId !== requestSessionId) return;
    const displayError = error?.name === "AbortError" ? new Error("请求超时，请稍后重试。") : error;
    renderChatError(displayError);
    renderDebugPanel({ error: String(error) });
  } finally {
    window.clearTimeout(timeoutId);
    if (state.activeChatRequest?.controller === controller) state.activeChatRequest = null;
    if (state.chatSessionId === requestSessionId) setFormDisabled(form, false);
  }
}

function renderChat(data) {
  const assistantNode = state.pendingAssistantNode || appendMessage("assistant", "", "助手");
  state.pendingAssistantNode = null;
  assistantNode.classList.remove("loading");
  assistantNode.querySelector(".message-meta").textContent = "助手";
  assistantNode.querySelector(".message-body").innerHTML = `
    <div class="message-meta">助手</div>
    <article class="answer-block">
      <div class="meta-row">
        <span>${escapeHtml(labelFor(labels.intents, data.intent || "unknown"))}</span>
        ${data.risk_level ? `<span>${escapeHtml(labelFor(labels.risks, data.risk_level))}</span>` : ""}
      </div>
      <div class="answer-text markdown-body">${renderMarkdown(data.answer || "暂无回答")}</div>
      ${renderFollowUps(data.follow_up_questions || [])}
      ${renderSources(data.sources || [])}
      ${renderToolSummary(data.tools_used || [])}
    </article>
  `;
  scrollChatToEnd();
}

function renderChatError(error) {
  const assistantNode = state.pendingAssistantNode || appendMessage("assistant", "", "助手");
  state.pendingAssistantNode = null;
  assistantNode.classList.remove("loading");
  assistantNode.querySelector(".message-body").innerHTML = `
    <div class="message-meta">请求失败</div>
    <p class="error-text">${escapeHtml(String(error))}</p>
  `;
}

function renderFollowUps(followUps) {
  const items = followUps.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  return items ? `<h3>追问信息</h3><ul>${items}</ul>` : "";
}

function renderSources(sources) {
  if (!sources.length) return "";
  const items = sources.map((source) => {
    const location = source.page ? `P${escapeHtml(source.page)}` : "";
    const section = source.section_title ? escapeHtml(source.section_title) : "";
    const sourceUri = source.source_uri ? `<code>${escapeHtml(source.source_uri)}</code>` : "";
    return `<li><strong>${escapeHtml(source.title || "未知来源")}</strong> ${location} ${section} ${sourceUri}</li>`;
  }).join("");
  return `<h3>引用</h3><ol class="source-list">${items}</ol>`;
}

function renderToolSummary(toolsUsed) {
  if (!toolsUsed.length) return "";
  const items = toolsUsed.map((tool) => `<span>${escapeHtml(tool)}</span>`).join("");
  return `<h3>工具</h3><div class="tool-list">${items}</div>`;
}

async function submitMeasurement(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const payload = {
    animal_id: formData.get("animal_id")?.toString() || "unknown",
    age_month: numberOrNull(formData.get("age_month")),
    current: {
      body_height_cm: numberOrNull(formData.get("body_height_cm")),
      body_length_cm: numberOrNull(formData.get("body_length_cm")),
      chest_girth_cm: numberOrNull(formData.get("chest_girth_cm")),
      weight_kg: numberOrNull(formData.get("weight_kg")),
    },
    confidence: numberOrNull(formData.get("confidence")),
    use_demo_history: formData.get("use_demo_history") === "on",
  };

  setFormDisabled(form, true);
  document.querySelector("#measurement-result").innerHTML = `<div class="empty-result">正在分析...</div>`;
  try {
    const response = await fetch("/api/measurement/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    renderMeasurement(data.data || {});
    renderDebugPanel(data);
  } catch (error) {
    document.querySelector("#measurement-result").innerHTML = `<p class="error-text">${escapeHtml(String(error))}</p>`;
    renderDebugPanel({ error: String(error) });
  } finally {
    setFormDisabled(form, false);
  }
}

function renderMeasurement(data) {
  const evidence = (data.evidence || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const abnormalItems = (data.abnormal_items || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  document.querySelector("#measurement-result").className = "measurement-result";
  document.querySelector("#measurement-result").innerHTML = `
    <article class="report-card">
      <div class="meta-row">
        <span>${escapeHtml(data.animal_id || "unknown")}</span>
        <span>${data.used_demo_history ? "演示历史" : "真实历史"}</span>
      </div>
      ${data.summary ? `<p><strong>${escapeHtml(data.summary)}</strong></p>` : ""}
      <p>${escapeHtml(data.report || "暂无报告")}</p>
    </article>
    ${abnormalItems ? `<section class="report-card"><h3>异常项</h3><div class="tool-list">${abnormalItems}</div></section>` : ""}
    ${data.recommendation ? `<section class="report-card"><h3>建议</h3><p>${escapeHtml(data.recommendation)}</p></section>` : ""}
    ${evidence ? `<section class="report-card"><h3>证据</h3><ul>${evidence}</ul></section>` : ""}
  `;
}

function appendMessage(role, text, meta, options = {}) {
  const container = document.querySelector("#chat-result");
  const node = document.createElement("article");
  node.className = `message ${role}-message${options.loading ? " loading" : ""}`;
  node.innerHTML = `
    <div class="message-avatar" aria-hidden="true">${role === "user" ? "你" : "R"}</div>
    <div class="message-body">
      <div class="message-meta">${escapeHtml(meta)}</div>
      <p>${escapeHtml(text)}</p>
    </div>
  `;
  container.appendChild(node);
  scrollChatToEnd();
  return node;
}

function renderStoredMessage(message) {
  const role = message.role === "user" ? "user" : "assistant";
  const node = appendMessage(role, "", role === "user" ? "你" : "助手");
  const body = node.querySelector(".message-body");
  const content = String(message.content || "");
  if (role === "user") {
    body.innerHTML = `<div class="message-meta">你</div><p>${escapeHtml(content)}</p>`;
    return;
  }
  body.innerHTML = `
    <div class="message-meta">助手</div>
    <article class="answer-block">
      ${(message.intent || message.risk_level) ? `<div class="meta-row">
        ${message.intent ? `<span>${escapeHtml(labelFor(labels.intents, message.intent))}</span>` : ""}
        ${message.risk_level ? `<span>${escapeHtml(labelFor(labels.risks, message.risk_level))}</span>` : ""}
      </div>` : ""}
      <div class="answer-text markdown-body">${renderMarkdown(content)}</div>
      ${renderFollowUps(Array.isArray(message.follow_up_questions) ? message.follow_up_questions : [])}
      ${renderSources(Array.isArray(message.sources) ? message.sources : [])}
      ${renderToolSummary(Array.isArray(message.tools_used) ? message.tools_used : [])}
      ${renderMessageErrors(Array.isArray(message.errors) ? message.errors : [])}
    </article>
  `;
}

function renderMessageErrors(errors) {
  const items = errors.map((error) => `<li>${escapeHtml(typeof error === "string" ? error : error.message || JSON.stringify(error))}</li>`).join("");
  return items ? `<details class="message-errors"><summary>处理提示</summary><ul>${items}</ul></details>` : "";
}

function cancelActiveChatRequest() {
  state.chatRequestToken += 1;
  if (state.activeChatRequest) state.activeChatRequest.controller.abort();
  state.activeChatRequest = null;
  state.pendingAssistantNode = null;
  state.pendingAssistantSessionId = null;
  setFormDisabled(document.querySelector("#chat-form"), false);
}

function persistCurrentSession(sessionId) {
  try {
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, sessionId);
  } catch {
    // The active session remains available in memory when storage is unavailable.
  }
}

function setCurrentSession(sessionId) {
  state.chatSessionId = sessionId;
  document.querySelector("#chat-form").dataset.sessionId = sessionId;
  persistCurrentSession(sessionId);
  document.querySelectorAll(".conversation-item").forEach((item) => {
    const isCurrent = item.dataset.sessionId === sessionId;
    item.classList.toggle("is-current", isCurrent);
    item.querySelector(".conversation-open")?.setAttribute("aria-current", isCurrent ? "page" : "false");
  });
}

function conversationTitle(conversation) {
  return String(conversation.title || conversation.summary || "新对话").trim() || "新对话";
}

function conversationTimestamp(conversation) {
  const value = conversation.updated_at || conversation.created_at;
  if (!value) return "";
  const date = parseConversationDate(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function conversationGroup(conversation) {
  const value = conversation.updated_at || conversation.created_at;
  const date = value ? parseConversationDate(value) : null;
  if (!date || Number.isNaN(date.getTime())) return "更早";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const itemDate = new Date(date);
  itemDate.setHours(0, 0, 0, 0);
  const days = Math.round((today - itemDate) / 86400000);
  if (days <= 0) return "今天";
  if (days < 7) return "最近 7 天";
  return "更早";
}

function parseConversationDate(value) {
  const normalized = String(value || "").trim().replace(" ", "T");
  if (!normalized) return new Date(Number.NaN);
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

function conversationPreview(conversation) {
  return String(conversation.preview || conversation.last_message || conversation.last_message_preview || "").trim();
}

function renderConversationItem(conversation) {
  const sessionId = String(conversation.session_id || conversation.id || "");
  const title = conversationTitle(conversation);
  const preview = conversationPreview(conversation);
  const isCurrent = sessionId === state.chatSessionId;
  return `
    <article class="conversation-item${isCurrent ? " is-current" : ""}" role="listitem" data-session-id="${escapeHtml(sessionId)}">
      <div class="conversation-open" role="button" tabindex="0" aria-label="打开对话：${escapeHtml(title)}" aria-current="${isCurrent ? "page" : "false"}">
        <span class="conversation-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
        ${preview ? `<span class="conversation-preview" title="${escapeHtml(preview)}">${escapeHtml(preview)}</span>` : ""}
        <time>${escapeHtml(conversationTimestamp(conversation))}</time>
      </div>
      <button class="conversation-menu-button" type="button" aria-label="${escapeHtml(title)}的更多操作" aria-expanded="false">•••</button>
      <div class="conversation-menu" hidden>
        <button type="button" data-action="rename">重命名</button>
        <button type="button" data-action="delete" class="danger-action">删除</button>
      </div>
    </article>
  `;
}

function renderConversationList(items, total = items.length) {
  const list = document.querySelector("#conversation-list");
  const count = document.querySelector("#conversation-count");
  state.conversations = items;
  state.conversationTotal = total;
  count.textContent = total ? String(total) : "";
  list.setAttribute("aria-busy", "false");
  if (!items.length) {
    const message = state.conversationSearch ? "没有匹配的对话" : "还没有历史对话";
    list.innerHTML = `<div class="history-state"><strong>${message}</strong><span>${state.conversationSearch ? "试试其他关键词" : "发送第一条消息后会显示在这里"}</span></div>`;
    return;
  }
  const groupOrder = ["今天", "最近 7 天", "更早"];
  const groupedHtml = groupOrder.map((group) => {
    const groupItems = items.filter((conversation) => conversationGroup(conversation) === group);
    if (!groupItems.length) return "";
    return `<section class="conversation-group" aria-labelledby="history-${group.replaceAll(" ", "-")}">
      <h3 id="history-${group.replaceAll(" ", "-")}">${group}</h3>
      ${groupItems.map(renderConversationItem).join("")}
    </section>`;
  }).join("");
  const loadMore = items.length < total
    ? `<button class="history-load-more" type="button">加载更多</button>`
    : "";
  list.innerHTML = `${groupedHtml}${loadMore}`;
}

function toggleSidebar() {
  const collapsed = document.body.classList.toggle("sidebar-collapsed");
  const button = document.querySelector("#sidebar-toggle");
  button.textContent = collapsed ? "›" : "‹";
  button.setAttribute("aria-expanded", String(!collapsed));
  button.setAttribute("aria-label", collapsed ? "展开对话历史" : "收起对话历史");
  try { window.localStorage.setItem("livestock_sidebar_collapsed", String(collapsed)); } catch { /* no-op */ }
}

async function loadConversationList(search = "", options = {}) {
  const list = document.querySelector("#conversation-list");
  const listToken = ++state.conversationListToken;
  const append = options.append === true;
  const offset = append ? state.conversations.length : 0;
  list.setAttribute("aria-busy", "true");
  try {
    const response = await fetch(`/api/conversations?search=${encodeURIComponent(search)}&limit=${state.conversationPageSize}&offset=${offset}`, {
      headers: { "X-Client-ID": state.clientId },
    });
    const payload = await response.json();
    if (!response.ok || payload.code !== 0) throw new Error(payload.message || "加载失败");
    if (listToken !== state.conversationListToken) return;
    const data = payload.data || {};
    const pageItems = Array.isArray(data.items) ? data.items : [];
    const items = append ? [...state.conversations, ...pageItems] : pageItems;
    renderConversationList(items, Number(data.total || 0));
  } catch (error) {
    if (listToken !== state.conversationListToken) return;
    list.setAttribute("aria-busy", "false");
    list.innerHTML = `<button class="history-retry" type="button">历史记录加载失败，点击重试</button>`;
    console.error("Failed to load conversations", error);
  }
}

async function openConversation(sessionId, options = {}) {
  if (!sessionId) return;
  cancelActiveChatRequest();
  const loadToken = ++state.conversationLoadToken;
  const thread = document.querySelector("#chat-result");
  const form = document.querySelector("#chat-form");
  setFormDisabled(form, true);
  thread.setAttribute("aria-busy", "true");
  if (!options.silent) thread.innerHTML = `<p class="history-state">正在加载对话…</p>`;
  try {
    const response = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}`, {
      headers: { "X-Client-ID": state.clientId },
    });
    const payload = await response.json();
    if (!response.ok || payload.code !== 0) {
      const historyError = new Error(payload.message || "对话加载失败");
      historyError.code = payload.code;
      throw historyError;
    }
    if (loadToken !== state.conversationLoadToken) return;
    const data = payload.data || {};
    const messages = Array.isArray(data.messages) ? data.messages : [];
    setCurrentSession(sessionId);
    thread.innerHTML = "";
    if (messages.length) {
      messages.forEach(renderStoredMessage);
    } else {
      appendMessage("assistant", "请描述具体场景、动物种类、症状或管理目标。", "系统待命");
    }
    setActiveView("chat");
    renderDebugPanel({});
    scrollChatToEnd();
  } catch (error) {
    if (loadToken !== state.conversationLoadToken) return;
    if (!options.silent) {
      thread.innerHTML = "";
      appendMessage("assistant", `无法加载该对话：${error.message || error}`, "加载失败");
    }
    if (options.clearMissing && error.code === 40004) startNewChatSession({ refresh: false });
  } finally {
    if (loadToken === state.conversationLoadToken) {
      thread.setAttribute("aria-busy", "false");
      setFormDisabled(form, false);
    }
  }
}

function closeConversationMenus() {
  state.openConversationMenu = null;
  document.querySelectorAll(".conversation-menu").forEach((menu) => { menu.hidden = true; });
  document.querySelectorAll(".conversation-menu-button").forEach((button) => button.setAttribute("aria-expanded", "false"));
}

function beginConversationRename(item) {
  closeConversationMenus();
  const titleNode = item.querySelector(".conversation-title");
  const originalTitle = titleNode.textContent.trim();
  titleNode.innerHTML = `<input class="conversation-rename-input" aria-label="新的对话名称" maxlength="80" value="${escapeHtml(originalTitle)}" />`;
  const input = titleNode.querySelector("input");
  input.focus();
  input.select();
  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const title = input.value.trim();
    titleNode.textContent = originalTitle;
    if (!save || !title || title === originalTitle) return;
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(item.dataset.sessionId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Client-ID": state.clientId },
        body: JSON.stringify({ title }),
      });
      const payload = await response.json();
      if (!response.ok || payload.code !== 0) throw new Error(payload.message || "重命名失败");
      await loadConversationList(state.conversationSearch);
    } catch (error) {
      window.alert(error.message || "重命名失败");
    }
  };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); finish(true); }
    if (event.key === "Escape") { event.preventDefault(); finish(false); }
  });
  input.addEventListener("blur", () => finish(true));
}

async function deleteConversation(item) {
  closeConversationMenus();
  const title = item.querySelector(".conversation-title").textContent.trim();
  if (!window.confirm(`确定删除“${title}”吗？此操作无法撤销。`)) return;
  const sessionId = item.dataset.sessionId;
  try {
    const response = await fetch(`/api/conversations/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      headers: { "X-Client-ID": state.clientId },
    });
    const payload = await response.json();
    if (!response.ok || payload.code !== 0) throw new Error(payload.message || "删除失败");
    if (sessionId === state.chatSessionId) startNewChatSession({ refresh: false });
    await loadConversationList(state.conversationSearch);
  } catch (error) {
    window.alert(error.message || "删除失败");
  }
}

function handleConversationListClick(event) {
  const item = event.target.closest(".conversation-item");
  if (event.target.closest(".history-retry")) { loadConversationList(state.conversationSearch); return; }
  if (event.target.closest(".history-load-more")) {
    loadConversationList(state.conversationSearch, { append: true });
    return;
  }
  if (!item) return;
  if (event.target.closest(".conversation-open") && !event.target.closest(".conversation-rename-input")) {
    closeConversationMenus();
    openConversation(item.dataset.sessionId);
    return;
  }
  const menuButton = event.target.closest(".conversation-menu-button");
  if (menuButton) {
    const menu = item.querySelector(".conversation-menu");
    const willOpen = menu.hidden;
    closeConversationMenus();
    menu.hidden = !willOpen;
    menuButton.setAttribute("aria-expanded", String(willOpen));
    state.openConversationMenu = willOpen ? item.dataset.sessionId : null;
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "rename") beginConversationRename(item);
  if (action === "delete") deleteConversation(item);
}

function handleConversationListKeydown(event) {
  if (event.target.closest(".conversation-rename-input")) return;
  const openButton = event.target.closest(".conversation-open");
  if (openButton && (event.key === "Enter" || event.key === " ")) {
    event.preventDefault();
    openConversation(openButton.closest(".conversation-item").dataset.sessionId);
  }
}

function scrollChatToEnd() {
  const container = document.querySelector("#chat-result");
  container.scrollTop = container.scrollHeight;
}

function setFormDisabled(form, disabled) {
  form.querySelectorAll("button, input, textarea").forEach((item) => {
    item.disabled = disabled;
  });
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function labelFor(dictionary, value) {
  return dictionary[value] || value;
}

function renderMarkdown(markdown) {
  const codeBlocks = [];
  const source = String(markdown || "")
    .replaceAll("\r\n", "\n")
    .replace(/```([^\n`]*)\n([\s\S]*?)```/g, (_, language, code) => {
      const safeLanguage = String(language || "").trim().replace(/[^a-z0-9_-]/gi, "");
      const languageClass = safeLanguage ? ` class="language-${safeLanguage}"` : "";
      const token = `\u0000CODE_BLOCK_${codeBlocks.length}\u0000`;
      codeBlocks.push(`<pre><code${languageClass}>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`);
      return `\n${token}\n`;
    });

  const output = [];
  let openList = null;
  const closeList = () => {
    if (openList) output.push(`</${openList}>`);
    openList = null;
  };

  source.split("\n").forEach((line) => {
    const codeMatch = line.match(/^\u0000CODE_BLOCK_(\d+)\u0000$/);
    if (codeMatch) {
      closeList();
      output.push(codeBlocks[Number(codeMatch[1])] || "");
      return;
    }
    if (!line.trim()) {
      closeList();
      return;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      output.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
      return;
    }
    const quote = line.match(/^>\s?(.*)$/);
    if (quote) {
      closeList();
      output.push(`<blockquote>${renderInlineMarkdown(quote[1])}</blockquote>`);
      return;
    }
    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    if (unordered) {
      if (openList !== "ul") {
        closeList();
        output.push("<ul>");
        openList = "ul";
      }
      output.push(`<li>${renderInlineMarkdown(unordered[1])}</li>`);
      return;
    }
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      if (openList !== "ol") {
        closeList();
        output.push("<ol>");
        openList = "ol";
      }
      output.push(`<li>${renderInlineMarkdown(ordered[1])}</li>`);
      return;
    }
    if (/^\s*---+\s*$/.test(line)) {
      closeList();
      output.push("<hr>");
      return;
    }

    closeList();
    output.push(`<p>${renderInlineMarkdown(line)}</p>`);
  });
  closeList();
  return output.join("");
}

function renderInlineMarkdown(text) {
  const inlineCode = [];
  let safe = escapeHtml(text).replace(/`([^`]+)`/g, (_, code) => {
    const token = `\u0000INLINE_CODE_${inlineCode.length}\u0000`;
    inlineCode.push(`<code>${code}</code>`);
    return token;
  });
  safe = safe.replace(/\[([^\]]+)]\(([^)\s]+)\)/g, (_, label, url) => {
    const decodedUrl = url.replaceAll("&amp;", "&");
    const safeUrl = sanitizeMarkdownUrl(decodedUrl);
    if (!safeUrl) return `${label} (${escapeHtml(decodedUrl)})`;
    return `<a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">${label}</a>`;
  });
  safe = safe
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>");
  inlineCode.forEach((html, index) => {
    safe = safe.replace(`\u0000INLINE_CODE_${index}\u0000`, html);
  });
  return safe;
}

function sanitizeMarkdownUrl(url) {
  const trimmed = String(url || "").trim();
  return /^(https?:\/\/|mailto:|#|\/(?!\/))/i.test(trimmed) ? trimmed : null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function getOrCreateChatSessionId() {
  try {
    const existing = window.localStorage.getItem(CHAT_SESSION_STORAGE_KEY);
    if (existing) return existing;
    const generated = `web_${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)}`;
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, generated);
    return generated;
  } catch {
    return `web_${Date.now().toString(36)}`;
  }
}

function getOrCreateClientId() {
  try {
    const existing = window.localStorage.getItem(CLIENT_ID_STORAGE_KEY);
    if (existing) return existing;
    const generated = `client_${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)}`;
    window.localStorage.setItem(CLIENT_ID_STORAGE_KEY, generated);
    return generated;
  } catch {
    return `client_${Date.now().toString(36)}`;
  }
}

function startNewChatSession(options = {}) {
  cancelActiveChatRequest();
  state.conversationLoadToken += 1;
  const generated = `web_${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36)}`;
  setCurrentSession(generated);
  state.pendingAssistantNode = null;
  state.lastResponse = null;
  try {
    window.localStorage.setItem(CHAT_SESSION_STORAGE_KEY, generated);
  } catch {
    // The in-memory session still works when local storage is unavailable.
  }
  document.querySelector("#chat-result").innerHTML = "";
  appendMessage("assistant", "请描述具体场景、动物种类、症状或管理目标。", "系统待命");
  renderDebugPanel({});
  document.querySelector("#chat-query").focus();
  if (options.refresh !== false) loadConversationList(state.conversationSearch);
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => setActiveView(tab.dataset.view));
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    const textarea = document.querySelector("#chat-query");
    textarea.value = button.dataset.prompt || "";
    textarea.focus();
  });
});

const chatForm = document.querySelector("#chat-form");
const chatQuery = document.querySelector("#chat-query");
chatForm.dataset.sessionId = state.chatSessionId || getOrCreateChatSessionId();
chatForm.addEventListener("submit", submitChat);
chatQuery.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
document.querySelector("#new-chat-button").addEventListener("click", startNewChatSession);
document.querySelector("#sidebar-toggle").addEventListener("click", toggleSidebar);
document.querySelector("#conversation-list").addEventListener("click", handleConversationListClick);
document.querySelector("#conversation-list").addEventListener("keydown", handleConversationListKeydown);
document.querySelector("#conversation-search").addEventListener("input", (event) => {
  state.conversationSearch = event.currentTarget.value.trim();
  window.clearTimeout(event.currentTarget.searchTimer);
  event.currentTarget.searchTimer = window.setTimeout(() => loadConversationList(state.conversationSearch), 250);
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".conversation-item")) closeConversationMenus();
});
document.querySelector("#measurement-form").addEventListener("submit", submitMeasurement);
loadRagStatus();
try {
  if (window.localStorage.getItem("livestock_sidebar_collapsed") === "true") toggleSidebar();
} catch {
  // Use the expanded sidebar when storage is unavailable.
}
loadConversationList();
openConversation(state.chatSessionId, { silent: true, clearMissing: true });
