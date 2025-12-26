function normalizeBaseUrl(baseUrl) {
  const url = (baseUrl || "").trim();
  return url.endsWith("/") ? url.slice(0, -1) : url;
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
    const detail = data?.detail || data?.raw || `HTTP ${res.status}`;
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

export async function startSession(baseUrl, nickname, quizId) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/start`, {
    method: "POST",
    body: JSON.stringify({ nickname, quiz_id: quizId })
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
