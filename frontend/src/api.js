function normalizeBaseUrl(baseUrl) {
  const url = (baseUrl || "").trim();
  return url.endsWith("/") ? url.slice(0, -1) : url;
}

function formatFastApiDetail(detail) {
  // FastAPI validation errors часто приходят как массив объектов
  if (Array.isArray(detail)) {
    return detail
      .map((x) => {
        const loc = Array.isArray(x?.loc) ? x.loc.join(".") : "";
        const msg = x?.msg ? String(x.msg) : JSON.stringify(x);
        return loc ? `${loc}: ${msg}` : msg;
      })
      .join("\n");
  }
  if (detail && typeof detail === "object") {
    try { return JSON.stringify(detail); } catch { return String(detail); }
  }
  return String(detail || "");
}

async function httpJson(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });

  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }

  if (!res.ok) {
    const detailRaw = data?.detail ?? data?.raw ?? `HTTP ${res.status}`;
    const detail = formatFastApiDetail(detailRaw) || `HTTP ${res.status}`;
    throw new Error(detail);
  }

  return data;
}

export async function getMeta(baseUrl, quizId) {
  const b = normalizeBaseUrl(baseUrl);
  const q = quizId ? `?quiz=${encodeURIComponent(quizId)}` : "";
  return httpJson(`${b}/api/meta${q}`, { method: "GET" });
}

export async function getQuestions(baseUrl, quizId) {
  const b = normalizeBaseUrl(baseUrl);
  const q = quizId ? `?quiz=${encodeURIComponent(quizId)}` : "";
  return httpJson(`${b}/api/questions${q}`, { method: "GET" });
}

export async function startSession(baseUrl, nickname, quizId, showInLeaderboard) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/start`, {
    method: "POST",
    body: JSON.stringify({
      nickname: (nickname || "").trim() || null,
      quiz_id: quizId,
      show_in_leaderboard: showInLeaderboard === true
    })
  });
}

export async function gradeAnswer(baseUrl, session_id, id, answer) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/grade`, {
    method: "POST",
    body: JSON.stringify({ session_id, id, answer })
  });
}

export async function getFinalFeedback(baseUrl, session_id) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/final_feedback`, {
    method: "POST",
    body: JSON.stringify({ session_id })
  });
}

export async function getLeaderboard(baseUrl, limit = 20) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/leaderboard?limit=${encodeURIComponent(limit)}`, {
    method: "GET"
  });
}
