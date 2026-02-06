import "./style.css";
import {
  getQuestions,
  gradeAnswer,
  getMeta,
  getFinalFeedback,
  startSession,
  getLeaderboard
} from "./api.js";

export function initQuizPage({ quizId }) {
  const els = {
    // start
    startCard: document.getElementById("start-card"),
    quizCard: document.getElementById("quiz-card"),

    nickname: document.getElementById("nickname"),
    backendUrl: document.getElementById("backend-url"),
    showInLeaderboard: document.getElementById("show-in-leaderboard"),
    btnStart: document.getElementById("btn-start"),
    startHint: document.getElementById("start-hint"),

    // quiz
    whoami: document.getElementById("whoami"),

    btnPrev: document.getElementById("btn-prev"),
    btnNext: document.getElementById("btn-next"),
    btnFinish: document.getElementById("btn-finish"),
    btnReload: document.getElementById("btn-reload"),
    btnResetProgress: document.getElementById("btn-reset-progress"),
    btnLeaderboard: document.getElementById("btn-leaderboard"),

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

    result: document.getElementById("result"),

    leaderboardCard: document.getElementById("leaderboard-card"),
    leaderboard: document.getElementById("leaderboard")
  };

  const STORAGE_INDEX_KEY = `ai_quiz_${quizId}_current_index_v1`;
  const STORAGE_PROGRESS_KEY = `ai_quiz_${quizId}_progress_v1`;
  const STORAGE_FINAL_KEY = `ai_quiz_${quizId}_final_v1`;
  const STORAGE_PROFILE_KEY = `ai_quiz_${quizId}_profile_v2`; // обновили версию (добавили show_in_leaderboard)

  const state = {
    quizId,
    questions: [],
    index: 0,
    passScore: 13,
    progress: { answers: {} },
    final: null, // { passed, message }
    profile: null // { nickname, session_id, show_in_leaderboard }
  };

  function setResult(text, tone = "muted") {
    els.result.className = `result ${tone}`;
    els.result.textContent = text;
  }

  function getBackendUrl() {
    const fromInput = (els.backendUrl.value || "").trim();
    return fromInput || "http://84.23.54.6:8000";
  }

  function lockUi(isLocked) {
    // start
    els.nickname.disabled = isLocked;
    if (els.showInLeaderboard) els.showInLeaderboard.disabled = isLocked;
    els.btnStart.disabled = isLocked;

    // quiz
    els.btnPrev.disabled = isLocked;
    els.btnNext.disabled = isLocked;
    els.btnFinish.disabled = isLocked;
    els.btnReload.disabled = isLocked;
    els.btnResetProgress.disabled = isLocked;
    els.btnLeaderboard.disabled = isLocked;

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
      return { passed: obj.passed === true, message: obj.message };
    } catch {
      return null;
    }
  }

  function saveProfile() {
    try { localStorage.setItem(STORAGE_PROFILE_KEY, JSON.stringify(state.profile)); } catch {}
  }

  function loadProfile() {
    try {
      const raw = localStorage.getItem(STORAGE_PROFILE_KEY);
      if (!raw) return null;
      const obj = JSON.parse(raw);
      if (!obj || typeof obj !== "object") return null;
      if (typeof obj.nickname !== "string") return null;
      if (typeof obj.session_id !== "string") return null;
      const show = obj.show_in_leaderboard === true;
      return { nickname: obj.nickname, session_id: obj.session_id, show_in_leaderboard: show };
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

  function renderWhoAmI() {
    const nick = state.profile?.nickname || "—";
    const pub = state.profile?.show_in_leaderboard === true ? " (в рейтинге)" : " (скрыто)";
    els.whoami.textContent = `Игрок: ${nick}${pub}`;
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
    renderWhoAmI();

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

  function formatFinalBlock(finalObj, passScore, stats) {
    const tone = finalObj.passed ? "ok" : "warn";
    const header = `🏁 Итог: ${stats.correct}/${stats.total} (порог ${passScore}) · Пройдено: ${stats.answered}/${stats.total}`;
    return { tone, text: `${header}\n\n${finalObj.message}` };
  }

  async function requestFinalFeedbackAndShow() {
    const { total, answered, correct, pass } = computeStats();
    if (total === 0) return;
    if (!state.profile?.session_id) return;

    setResult("🏁 Фиксирую результат…");
    lockUi(true);

    try {
      const r = await getFinalFeedback(getBackendUrl(), state.profile.session_id);
      const passed = r?.passed === true;
      const message = String(r?.message || "").trim() || "Отзыв пустой, но итог зафиксирован.";

      state.final = { passed, message };
      saveFinal();

      const view = formatFinalBlock(state.final, pass, { total, answered, correct });
      setResult(view.text, view.tone);
    } catch (e) {
      setResult(`Ошибка финального отзыва: ${e?.message || e}`, "bad");
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
        const m = await getMeta(getBackendUrl(), state.quizId);
        if (Number.isFinite(Number(m?.pass_score))) state.passScore = Number(m.pass_score);
      } catch {}

      const data = await getQuestions(getBackendUrl(), state.quizId);
      const list = Array.isArray(data?.questions) ? data.questions : [];

      state.questions = list.filter(x => x && typeof x.id === "string" && typeof x.question === "string");
      state.index = clampIndex(loadIndex());

      state.progress = loadProgress();
      state.final = loadFinal();

      renderQuestion();
      setResult("Готово.", "ok");
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
    await requestFinalFeedbackAndShow();
    await refreshLeaderboard();
  }

  async function onGrade(e) {
    e.preventDefault();

    if (!state.profile?.session_id) {
      setResult("Сначала нажмите «Начать» и получите session_id.", "bad");
      return;
    }

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
      const r = await gradeAnswer(getBackendUrl(), state.profile.session_id, q.id, answer);

      const ok = r.ok === true;
      const feedback = (r.feedback || "").trim();

      state.final = null;
      try { localStorage.removeItem(STORAGE_FINAL_KEY); } catch {}

      state.progress.answers[q.id] = { answer, ok, feedback };
      saveProgress();

      const serverLine = (Number.isFinite(Number(r.correct)) && Number.isFinite(Number(r.answered)))
        ? `\n\n[server] correct=${r.correct}, answered=${r.answered}, total=${r.total}`
        : "";

      setResult(`ok: ${ok}\n\n${feedback || "(нет комментария)"}${serverLine}`, ok ? "ok" : "warn");

      renderQuestionStatus(q.id);
      renderTopProgress();
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

  function showStart() {
    els.startCard.style.display = "";
    els.quizCard.style.display = "none";
    els.leaderboardCard.style.display = "none";
  }

  function showQuiz() {
    els.startCard.style.display = "none";
    els.quizCard.style.display = "";
    els.leaderboardCard.style.display = "";
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

    const rows = items.map((x, idx) => {
      const n = String(x.nickname || "—");
      const c = Number(x.best_correct) || 0;
      const a = Number(x.best_answered) || 0;
      const t = String(x.last_activity_at || "—");
      const me = (state.profile?.nickname && n === state.profile.nickname && state.profile?.show_in_leaderboard)
        ? `<span class="badge">ты</span>` : "";
      return `
        <div class="leaderboard-row">
          <div>${idx + 1}</div>
          <div>${escapeHtml(n)} ${me}</div>
          <div>${c}</div>
          <div>${a}</div>
          <div>${escapeHtml(t)}</div>
        </div>
      `;
    }).join("");

    els.leaderboard.innerHTML = head + rows;
  }

  async function refreshLeaderboard() {
    try {
      const r = await getLeaderboard(getBackendUrl(), 20);
      renderLeaderboard(r?.items || []);
      els.leaderboardCard.style.display = "";
    } catch (e) {
      els.leaderboard.textContent = `Не удалось загрузить рейтинг: ${e?.message || e}`;
      els.leaderboardCard.style.display = "";
    }
  }

  async function onStart() {
    const nickname = (els.nickname.value || "").trim();
    const show = els.showInLeaderboard ? (els.showInLeaderboard.checked === true) : false;

    if (show && !nickname) {
      setResult("Чтобы попасть в рейтинг, нужно указать никнейм (или снимите галочку «Показывать в рейтинге»).", "bad");
      return;
    }

    setResult("Создаю сессию…");
    lockUi(true);

    try {
      const s = await startSession(getBackendUrl(), nickname, state.quizId, show);
      const session_id = String(s?.session_id || "").trim();
      const nick = String(s?.nickname || (nickname || "guest")).trim();
      const pub = s?.show_in_leaderboard === true;

      if (!session_id) throw new Error("Сервер не вернул session_id");

      state.profile = { nickname: nick, session_id, show_in_leaderboard: pub };
      saveProfile();

      showQuiz();
      renderQuestion();
      await loadQuestionsFromBackend();
      await refreshLeaderboard();

      setResult(
        `Сессия создана ✅\nquiz_id: ${state.quizId}\nnickname: ${nick}\nshow_in_leaderboard: ${pub}\nsession_id: ${session_id}`,
        "ok"
      );
    } catch (e) {
      setResult(`Ошибка старта: ${e?.message || e}`, "bad");
    } finally {
      lockUi(false);
    }
  }

  function init() {
    els.backendUrl.value = "http://scen4ri0.info:8000"
    state.profile = loadProfile();
    state.progress = loadProgress();
    state.final = loadFinal();

    if (state.profile?.session_id && state.profile?.nickname) {
      els.nickname.value = state.profile.nickname.startsWith("guest-") ? "" : state.profile.nickname;
      if (els.showInLeaderboard) els.showInLeaderboard.checked = state.profile.show_in_leaderboard === true;
      showQuiz();
    } else {
      showStart();
    }

    els.btnStart.addEventListener("click", onStart);

    els.btnPrev.addEventListener("click", onPrev);
    els.btnNext.addEventListener("click", onNext);
    els.btnFinish.addEventListener("click", onFinish);

    els.btnReload.addEventListener("click", loadQuestionsFromBackend);
    els.btnResetProgress.addEventListener("click", onResetProgress);
    els.btnLeaderboard.addEventListener("click", refreshLeaderboard);

    els.answerForm.addEventListener("submit", onGrade);
    els.btnClear.addEventListener("click", onClear);

    renderQuestion();
    if (els.quizCard.style.display !== "none") {
      loadQuestionsFromBackend();
      refreshLeaderboard();
    }
  }

  init();
}
