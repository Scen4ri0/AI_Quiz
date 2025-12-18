import "./style.css";
import { getQuestions, gradeAnswer, getMeta, getFinalFeedback } from "./api.js";

const els = {
  backendUrl: document.getElementById("backend-url"),

  btnPrev: document.getElementById("btn-prev"),
  btnNext: document.getElementById("btn-next"),
  btnFinish: document.getElementById("btn-finish"),
  btnReload: document.getElementById("btn-reload"),
  btnResetProgress: document.getElementById("btn-reset-progress"),

  progress: document.getElementById("progress"),
  scoreline: document.getElementById("scoreline"),
  progressbarFill: document.getElementById("progressbar-fill"),

  questionText: document.getElementById("question-text"),
  questionId: document.getElementById("question-id"),
  questionStatus: document.getElementById("question-status"),

  answerForm: document.getElementById("answer-form"),
  answer: document.getElementById("answer"),
  btnGrade: document.getElementById("btn-grade"),
  btnClear: document.getElementById("btn-clear"),

  result: document.getElementById("result")
};

const STORAGE_INDEX_KEY = "ai_quiz_current_index_v1";
const STORAGE_PROGRESS_KEY = "ai_quiz_progress_v1";
const STORAGE_FINAL_KEY = "ai_quiz_final_v2";

const state = {
  questions: [],
  index: 0,
  passScore: 13,
  progress: { answers: {} },
  final: null // { passed, message, correct, answered, total }
};

function setResult(text, tone = "muted") {
  els.result.className = `result ${tone}`;
  els.result.textContent = text;
}

function getBackendUrl() {
  const fromInput = els.backendUrl.value.trim();
  return fromInput || "http://localhost:8000";
}

function lockUi(isLocked) {
  els.btnPrev.disabled = isLocked;
  els.btnNext.disabled = isLocked;
  els.btnFinish.disabled = isLocked;
  els.btnReload.disabled = isLocked;
  els.btnResetProgress.disabled = isLocked;

  els.btnGrade.disabled = isLocked;
  els.btnClear.disabled = isLocked;

  els.backendUrl.disabled = isLocked;
  els.answer.disabled = isLocked;
}

function saveIndex() {
  try { localStorage.setItem(STORAGE_INDEX_KEY, String(state.index)); } catch {}
}

function loadIndex() {
  try {
    const v = localStorage.getItem(STORAGE_INDEX_KEY);
    if (!v) return 0;
    const n = Number(v);
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

function saveProgress() {
  try { localStorage.setItem(STORAGE_PROGRESS_KEY, JSON.stringify(state.progress)); } catch {}
}

function loadProgress() {
  try {
    const raw = localStorage.getItem(STORAGE_PROGRESS_KEY);
    if (!raw) return { answers: {} };
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== "object") return { answers: {} };
    if (!obj.answers || typeof obj.answers !== "object") return { answers: {} };
    return { answers: obj.answers };
  } catch {
    return { answers: {} };
  }
}

function saveFinal() {
  try { localStorage.setItem(STORAGE_FINAL_KEY, JSON.stringify(state.final)); } catch {}
}

function loadFinal() {
  try {
    const raw = localStorage.getItem(STORAGE_FINAL_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (!obj || typeof obj !== "object") return null;
    if (typeof obj.message !== "string") return null;
    return {
      passed: obj.passed === true,
      message: obj.message,
      correct: Number(obj.correct) || 0,
      answered: Number(obj.answered) || 0,
      total: Number(obj.total) || 0
    };
  } catch {
    return null;
  }
}

function clampIndex(i) {
  if (state.questions.length === 0) return 0;
  return Math.max(0, Math.min(i, state.questions.length - 1));
}

function computeStats() {
  const ids = state.questions.map(q => q.id);
  let answered = 0;
  let correct = 0;

  for (const id of ids) {
    const a = state.progress.answers[id];
    if (a && typeof a.ok === "boolean") {
      answered += 1;
      if (a.ok === true) correct += 1;
    }
  }

  return { total: ids.length, answered, correct, pass: state.passScore };
}

function renderTopProgress() {
  const { total, answered, correct, pass } = computeStats();

  if (total === 0) {
    els.progress.textContent = "Вопрос: —";
    els.scoreline.textContent = "Счёт: —";
    els.progressbarFill.style.width = "0%";
    return;
  }

  els.progress.textContent = `Вопрос: ${state.index + 1} / ${total} · Отвечено: ${answered} / ${total}`;
  els.scoreline.textContent = `Верно: ${correct} · Нужно: ${pass} / ${total}`;

  const pct = Math.round((answered / total) * 100);
  els.progressbarFill.style.width = `${pct}%`;
}

function renderQuestionStatus(qid) {
  const a = state.progress.answers[qid];
  if (!a || typeof a.ok !== "boolean") {
    els.questionStatus.textContent = "Статус: ещё не проверено.";
    return;
  }
  els.questionStatus.textContent = a.ok ? "Статус: ✅ верно (сохранено)." : "Статус: ⚠️ неверно (сохранено).";
}

function renderQuestion() {
  if (state.questions.length === 0) {
    els.questionText.textContent = "Нет вопросов. Нажмите “Перезагрузить список”.";
    els.questionId.textContent = "";
    els.questionStatus.textContent = "";
    els.btnPrev.disabled = true;
    els.btnNext.disabled = true;
    renderTopProgress();
    return;
  }

  state.index = clampIndex(state.index);
  const q = state.questions[state.index];

  els.questionText.textContent = q.question;
  els.questionId.textContent = `id: ${q.id}`;

  const saved = state.progress.answers[q.id];
  els.answer.value = saved?.answer ? String(saved.answer) : "";

  renderQuestionStatus(q.id);
  renderTopProgress();

  els.btnPrev.disabled = state.index === 0;
  els.btnNext.disabled = state.index === state.questions.length - 1;
}

function formatFinalBlock(finalObj, passScore) {
  const correct = finalObj.correct;
  const answered = finalObj.answered;
  const total = finalObj.total;
  const tone = finalObj.passed ? "ok" : "warn";

  const header = `🏁 Итог: ${correct}/${total} (порог ${passScore}) · Пройдено: ${answered}/${total}`;
  return { tone, text: `${header}\n\n${finalObj.message}` };
}

async function requestFinalFeedbackAndShow({ force = false } = {}) {
  const { total, answered, correct, pass } = computeStats();
  if (total === 0) return;

  // если не форсим — авто-итог только когда 20/20
  if (!force && answered < total) return;

  // если уже запрашивали такой же итог — просто покажем
  if (
    state.final &&
    state.final.total === total &&
    state.final.answered === answered &&
    state.final.correct === correct &&
    typeof state.final.message === "string"
  ) {
    const view = formatFinalBlock(state.final, pass);
    setResult(view.text, view.tone);
    return;
  }

  setResult("🏁 Фиксирую результат… сейчас будет отзыв 😎");
  lockUi(true);

  try {
    const r = await getFinalFeedback(getBackendUrl(), correct, answered);

    const passed = r?.passed === true;
    const message = String(r?.message || "").trim() || "Отзыв пустой, но итог зафиксирован.";

    state.final = { passed, message, correct, answered, total };
    saveFinal();

    const view = formatFinalBlock(state.final, pass);
    setResult(view.text, view.tone);
  } catch (e) {
    // На практике тут почти не должно быть ошибок, потому что backend теперь всегда отдаёт 200.
    const fallback = {
      passed: correct >= pass,
      message: "Не удалось получить отзыв. Но результат посчитан локально.",
      correct,
      answered,
      total
    };
    const view = formatFinalBlock(fallback, pass);
    setResult(view.text, view.tone);
  } finally {
    lockUi(false);
    renderQuestion();
  }
}

async function loadQuestionsFromBackend() {
  setResult("Загружаю список вопросов…");
  lockUi(true);

  try {
    try {
      const m = await getMeta(getBackendUrl());
      if (Number.isFinite(Number(m?.pass_score))) state.passScore = Number(m.pass_score);
    } catch {}

    const data = await getQuestions(getBackendUrl());
    const list = Array.isArray(data?.questions) ? data.questions : [];

    state.questions = list.filter(x => x && typeof x.id === "string" && typeof x.question === "string");
    state.index = clampIndex(loadIndex());

    state.progress = loadProgress();
    state.final = loadFinal();

    renderQuestion();
    setResult("Готово.", "ok");

    // если уже завершали на этом прогрессе — покажем сохранённый итог
    await requestFinalFeedbackAndShow({ force: false });
  } catch (e) {
    setResult(`Ошибка загрузки вопросов: ${e?.message || e}`, "bad");
  } finally {
    lockUi(false);
  }
}

function onPrev() {
  if (state.questions.length === 0) return;
  state.index = clampIndex(state.index - 1);
  saveIndex();
  setResult("Пока нет результата.");
  renderQuestion();
}

function onNext() {
  if (state.questions.length === 0) return;
  state.index = clampIndex(state.index + 1);
  saveIndex();
  setResult("Пока нет результата.");
  renderQuestion();
}

async function onFinish() {
  // Завершить тест в любой момент
  await requestFinalFeedbackAndShow({ force: true });
}

async function onGrade(e) {
  e.preventDefault();

  if (state.questions.length === 0) {
    setResult("Список вопросов пуст. Перезагрузите список.", "bad");
    return;
  }

  const answer = els.answer.value.trim();
  if (!answer) {
    setResult("Введите суть ответа (1–2 ключевые идеи).", "bad");
    return;
  }

  const q = state.questions[state.index];

  setResult("Проверяю ответ через LLM…");
  lockUi(true);

  try {
    const r = await gradeAnswer(getBackendUrl(), q.id, answer);

    const ok = r.ok === true;
    const feedback = (r.feedback || "").trim();

    // новый ответ меняет статистику — сбрасываем кэш итога
    state.final = null;
    try { localStorage.removeItem(STORAGE_FINAL_KEY); } catch {}

    state.progress.answers[q.id] = { answer, ok, feedback };
    saveProgress();

    setResult(`ok: ${ok}\n\n${feedback || "(нет комментария)"}`, ok ? "ok" : "warn");

    renderQuestionStatus(q.id);
    renderTopProgress();

    // авто-итог только когда всё отвечено
    await requestFinalFeedbackAndShow({ force: false });
  } catch (e2) {
    setResult(`Ошибка проверки: ${e2?.message || e2}`, "bad");
  } finally {
    lockUi(false);
    renderQuestion();
  }
}

function onClear() {
  els.answer.value = "";
  setResult("Очищено.", "muted");
}

function onResetProgress() {
  try {
    localStorage.removeItem(STORAGE_PROGRESS_KEY);
    localStorage.removeItem(STORAGE_INDEX_KEY);
    localStorage.removeItem(STORAGE_FINAL_KEY);
  } catch {}

  state.progress = { answers: {} };
  state.final = null;
  state.index = 0;

  setResult("Прогресс сброшен.", "muted");
  renderQuestion();
}

function init() {
  els.backendUrl.value = "http://localhost:8000";

  els.btnPrev.addEventListener("click", onPrev);
  els.btnNext.addEventListener("click", onNext);
  els.btnFinish.addEventListener("click", onFinish);

  els.btnReload.addEventListener("click", loadQuestionsFromBackend);
  els.btnResetProgress.addEventListener("click", onResetProgress);

  els.answerForm.addEventListener("submit", onGrade);
  els.btnClear.addEventListener("click", onClear);

  state.progress = loadProgress();
  state.final = loadFinal();

  renderQuestion();
  loadQuestionsFromBackend();
}

init();
