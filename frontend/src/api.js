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

export async function getMeta(baseUrl) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/meta`, { method: "GET" });
}

export async function getQuestions(baseUrl) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/questions`, { method: "GET" });
}

export async function gradeAnswer(baseUrl, id, answer) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/grade`, {
    method: "POST",
    body: JSON.stringify({ id, answer })
  });
}

export async function getFinalFeedback(baseUrl, correct, answered) {
  const b = normalizeBaseUrl(baseUrl);
  return httpJson(`${b}/api/final_feedback`, {
    method: "POST",
    body: JSON.stringify({ correct, answered })
  });
}
