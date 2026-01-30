import "./style.css";
import { getLeaderboard } from "./api.js";

const els = {
  backendUrl: document.getElementById("backend-url"),
  btnRefresh: document.getElementById("btn-refresh"),
  leaderboard: document.getElementById("leaderboard"),
  result: document.getElementById("result"),
};

function getBackendUrl() {
  const v = (els.backendUrl.value || "").trim();
  return v || "http://84.23.54.6:8000";
}

function setResult(text, tone = "muted") {
  els.result.className = `result ${tone}`;
  els.result.textContent = text;
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderLeaderboard(items) {
  if (!Array.isArray(items) || items.length === 0) {
    els.leaderboard.textContent = "Пока пусто.";
    return;
  }

  const head = `
    <div class="leaderboard-row leaderboard-head">
      <div>#</div>
      <div>ник</div>
      <div>best correct</div>
      <div>best answered</div>
      <div>активность</div>
    </div>
  `;

  const rows = items
    .map((x, idx) => {
      const n = String(x.nickname || "—");
      const c = Number(x.best_correct) || 0;
      const a = Number(x.best_answered) || 0;
      const t = String(x.last_activity_at || "—");
      return `
        <div class="leaderboard-row">
          <div>${idx + 1}</div>
          <div>${escapeHtml(n)}</div>
          <div>${c}</div>
          <div>${a}</div>
          <div>${escapeHtml(t)}</div>
        </div>
      `;
    })
    .join("");

  els.leaderboard.innerHTML = head + rows;
}

async function refresh() {
  setResult("Загружаю рейтинг…");
  try {
    const r = await getLeaderboard(getBackendUrl(), 50);
    renderLeaderboard(r?.items || []);
    setResult("Готово.", "ok");
  } catch (e) {
    els.leaderboard.textContent = "Ошибка загрузки.";
    setResult(`Ошибка: ${e?.message || e}`, "bad");
  }
}

function init() {
  els.backendUrl.value = "http://84.23.54.6:8000";
  els.btnRefresh.addEventListener("click", refresh);
  refresh();
}

init();
