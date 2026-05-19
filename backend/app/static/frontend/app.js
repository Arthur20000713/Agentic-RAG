const state = {
  lastResponse: null,
  ragStatus: null,
  pendingAssistantNode: null,
};

const labels = {
  intents: {
    general_qa: "知识问答",
    disease_consultation: "疾病问诊",
    measurement_analysis: "体尺分析",
    out_of_scope: "超出范围",
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

  appendMessage("user", query, "你");
  state.pendingAssistantNode = appendMessage("assistant", "正在检索和整理证据...", "处理中", { loading: true });
  setFormDisabled(form, true);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    const payload = await response.json();
    renderChat(payload.data || {});
    renderDebugPanel(payload);
    form.reset();
  } catch (error) {
    renderChatError(error);
    renderDebugPanel({ error: String(error) });
  } finally {
    setFormDisabled(form, false);
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
      <p class="answer-text">${escapeHtml(data.answer || "暂无回答")}</p>
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

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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

document.querySelector("#chat-form").addEventListener("submit", submitChat);
document.querySelector("#measurement-form").addEventListener("submit", submitMeasurement);
loadRagStatus();
