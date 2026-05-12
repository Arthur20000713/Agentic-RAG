const state = {
  lastResponse: null,
  ragStatus: null,
};

function setActiveView(viewName) {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.view === viewName);
  });
  document.querySelectorAll(".view").forEach((view) => {
    view.classList.toggle("is-active", view.id === `${viewName}-view`);
  });
}

function renderDebugPanel(payload) {
  state.lastResponse = payload;
  const summary = buildDebugSummary(payload || {});
  document.querySelector("#debug-json").textContent = JSON.stringify({ summary, raw: payload || {} }, null, 2);
}

function buildDebugSummary(payload) {
  const data = payload.data || {};
  return {
    request_id: payload.request_id || data.request_id || null,
    rag_mode: data.rag_mode_effective || data.rag_mode || state.ragStatus?.rag_mode_effective || state.ragStatus?.rag_mode || null,
    agent_path: data.agent_path || nodesFromTrace(data.agent_trace) || data.tools_used || [],
    safety: data.safety_result || data.safety || "not_available",
    verifier: data.verification_result || data.verifier_result || "not_available",
  };
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
  const query = new FormData(event.currentTarget).get("query")?.toString().trim();
  if (!query) return;
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  const payload = await response.json();
  renderChat(payload.data || {});
  renderDebugPanel(payload);
}

function renderChat(data) {
  const container = document.querySelector("#chat-result");
  const followUps = (data.follow_up_questions || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  container.innerHTML = `
    <article class="answer-block">
      <div class="meta-row">
        <span>${escapeHtml(data.intent || "unknown")}</span>
        ${data.risk_level ? `<span>${escapeHtml(data.risk_level)}</span>` : ""}
      </div>
      <p>${escapeHtml(data.answer || "暂无回答")}</p>
      ${followUps ? `<h3>追问信息</h3><ul>${followUps}</ul>` : ""}
      ${renderSources(data.sources || [])}
      ${renderToolSummary(data.tools_used || [])}
    </article>
  `;
}

function renderSources(sources) {
  if (!sources.length) return "";
  const items = sources.map((source) => {
    const location = source.page ? `P${escapeHtml(source.page)}` : "";
    const section = source.section_title ? escapeHtml(source.section_title) : "";
    const sourceUri = source.source_uri ? `<code>${escapeHtml(source.source_uri)}</code>` : "";
    return `<li><strong>${escapeHtml(source.title || "未知来源")}</strong> ${location} ${section} ${sourceUri}</li>`;
  }).join("");
  return `<h3>引用</h3><ul class="source-list">${items}</ul>`;
}

function renderToolSummary(toolsUsed) {
  if (!toolsUsed.length) return "";
  const items = toolsUsed.map((tool) => `<span>${escapeHtml(tool)}</span>`).join("");
  return `<h3>工具</h3><div class="tool-list">${items}</div>`;
}

async function submitMeasurement(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    animal_id: form.get("animal_id")?.toString() || "unknown",
    current: {
      chest_girth_cm: numberOrNull(form.get("chest_girth_cm")),
      weight_kg: numberOrNull(form.get("weight_kg")),
    },
    confidence: numberOrNull(form.get("confidence")),
    use_demo_history: form.get("use_demo_history") === "on",
  };
  const response = await fetch("/api/measurement/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  renderMeasurement(data.data || {});
  renderDebugPanel(data);
}

function renderMeasurement(data) {
  const evidence = (data.evidence || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const abnormalItems = (data.abnormal_items || []).map((item) => `<span>${escapeHtml(item)}</span>`).join("");
  document.querySelector("#measurement-result").innerHTML = `
    <article class="answer-block">
      ${data.summary ? `<p><strong>${escapeHtml(data.summary)}</strong></p>` : ""}
      <p>${escapeHtml(data.report || "暂无报告")}</p>
      ${abnormalItems ? `<h3>异常项</h3><div class="tool-list">${abnormalItems}</div>` : ""}
      ${evidence ? `<h3>证据</h3><ul>${evidence}</ul>` : ""}
    </article>
  `;
}

function numberOrNull(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
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
document.querySelector("#chat-form").addEventListener("submit", submitChat);
document.querySelector("#measurement-form").addEventListener("submit", submitMeasurement);
loadRagStatus();
