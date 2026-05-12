const state = {
  lastResponse: null,
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
  document.querySelector("#debug-json").textContent = JSON.stringify(payload || {}, null, 2);
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
  container.innerHTML = `
    <article class="answer-block">
      <div class="meta-row">
        <span>${escapeHtml(data.intent || "unknown")}</span>
        ${data.risk_level ? `<span>${escapeHtml(data.risk_level)}</span>` : ""}
      </div>
      <p>${escapeHtml(data.answer || "暂无回答")}</p>
    </article>
  `;
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
  document.querySelector("#measurement-result").innerHTML = `
    <article class="answer-block">
      <p>${escapeHtml(data.report || "暂无报告")}</p>
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
