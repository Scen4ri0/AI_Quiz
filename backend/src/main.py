# -*- coding: utf-8 -*-
import json
import os
import traceback
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from grader import GradeResult, grade_answer, FinalFeedbackOut, final_feedback_safe
from db import init_db, create_session, apply_answer_result, finish_session, leaderboard, get_session_meta

# --- Загружаем backend/.env, если он есть ---
try:
    from dotenv import load_dotenv  # type: ignore

    ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=ENV_PATH, override=False)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_QUIZ1_PATH = BASE_DIR / "questions.json"
QUESTIONS_QUIZ2_PATH = BASE_DIR / "questions_quiz2.json"

PASS_SCORE = int(os.getenv("PASS_SCORE", "13"))


def _load_questions_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"questions file not found at: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError(f"{path.name} must contain a JSON array")
    return data


QUESTIONS_BY_QUIZ: dict[str, list[dict[str, Any]]] = {
    "quiz1": _load_questions_file(QUESTIONS_QUIZ1_PATH),
    "quiz2": _load_questions_file(QUESTIONS_QUIZ2_PATH),
}

QUIZ_TITLES: dict[str, str] = {
    "quiz1": "Тест 1 (LLM основы)",
    "quiz2": "Тест 2 (RAG / Vector DB / Agents)",
}

app = FastAPI(title="AI Quiz Backend", version="0.9.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "y", "on"}


@app.on_event("startup")
def _startup() -> None:
    init_db()


class QuestionOut(BaseModel):
    id: str
    question: str


class QuestionsListOut(BaseModel):
    quiz_id: str
    questions: list[QuestionOut]
    total: int
    pass_score: int


class QuizMetaOut(BaseModel):
    quiz_id: str
    title: str
    total: int
    pass_score: int


class QuizItemOut(BaseModel):
    quiz_id: str
    title: str
    total: int
    pass_score: int


class QuizzesOut(BaseModel):
    items: list[QuizItemOut]


class StartIn(BaseModel):
    # ✅ nickname теперь НЕ обязательный
    nickname: str | None = Field(
        None,
        min_length=0,
        max_length=40,
        description="Имя/ник без пароля. Можно не вводить — будет гостевой проход.",
    )
    quiz_id: str = Field("quiz1", description="ID теста: quiz1 или quiz2")
    # ✅ флаг: показывать или нет в рейтинге
    show_in_leaderboard: bool = Field(
        False,
        description="Если true — попытка будет учитываться в лидерборде. Если nickname пустой, всегда false.",
    )


class StartOut(BaseModel):
    session_id: str
    nickname: str
    quiz_id: str
    total: int
    pass_score: int
    show_in_leaderboard: bool


class GradeIn(BaseModel):
    session_id: str = Field(..., min_length=8, description="ID сессии из /api/start")
    id: str = Field(..., description="ID вопроса из questions")
    answer: str = Field(..., min_length=1, description="Короткий ответ пользователя (суть)")


class GradeOut(GradeResult):
    correct: int
    answered: int
    total: int
    pass_score: int


class FinalFeedbackIn(BaseModel):
    session_id: str = Field(..., min_length=8)


class LeaderboardOut(BaseModel):
    items: list[dict[str, Any]]


def _require_quiz_id(quiz_id: str | None) -> str:
    q = (quiz_id or "").strip() or "quiz1"
    if q not in QUESTIONS_BY_QUIZ:
        raise HTTPException(status_code=400, detail=f"Unknown quiz_id: {q}")
    return q


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/quizzes", response_model=QuizzesOut)
def quizzes() -> QuizzesOut:
    items: list[QuizItemOut] = []
    for qid, qs in QUESTIONS_BY_QUIZ.items():
        items.append(
            QuizItemOut(
                quiz_id=qid,
                title=QUIZ_TITLES.get(qid, qid),
                total=len(qs),
                pass_score=PASS_SCORE,
            )
        )
    return QuizzesOut(items=items)


@app.get("/api/meta", response_model=QuizMetaOut)
def meta(quiz: str = "quiz1") -> QuizMetaOut:
    qid = _require_quiz_id(quiz)
    qs = QUESTIONS_BY_QUIZ[qid]
    return QuizMetaOut(
        quiz_id=qid,
        title=QUIZ_TITLES.get(qid, qid),
        total=len(qs),
        pass_score=PASS_SCORE,
    )


@app.get("/api/questions", response_model=QuestionsListOut)
def list_questions(quiz: str = "quiz1") -> QuestionsListOut:
    qid = _require_quiz_id(quiz)
    qs = QUESTIONS_BY_QUIZ[qid]

    out: list[QuestionOut] = []
    for q in qs:
        qqid = q.get("id")
        text = q.get("question")
        if isinstance(qqid, str) and isinstance(text, str) and text.strip():
            out.append(QuestionOut(id=qqid, question=text))

    return QuestionsListOut(quiz_id=qid, questions=out, total=len(out), pass_score=PASS_SCORE)


@app.post("/api/start", response_model=StartOut)
def start(payload: StartIn) -> StartOut:
    # ✅ nickname может быть пустым/None
    raw = (payload.nickname or "").strip()
    nickname = " ".join(raw.split())  # нормализация пробелов

    quiz_id = _require_quiz_id(payload.quiz_id)
    total = len(QUESTIONS_BY_QUIZ[quiz_id])

    # ✅ если ника нет — это всегда "скрытый" гостевой проход
    show = bool(payload.show_in_leaderboard) and bool(nickname)

    try:
        s = create_session(
            nickname=nickname if nickname else None,
            total=total,
            pass_score=PASS_SCORE,
            quiz_id=quiz_id,
            is_public=show,
        )
        return StartOut(
            session_id=str(s["session_id"]),
            nickname=str(s["nickname"]),
            quiz_id=str(s["quiz_id"]),
            total=total,
            pass_score=PASS_SCORE,
            show_in_leaderboard=bool(s["is_public"]),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        if DEBUG:
            raise HTTPException(status_code=500, detail=f"Start failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Start failed")


@app.post("/api/grade", response_model=GradeOut)
def grade(payload: GradeIn) -> GradeOut:
    meta_s = get_session_meta(payload.session_id)
    if not meta_s:
        raise HTTPException(status_code=404, detail="Session not found")

    quiz_id = str(meta_s.get("quiz_id") or "quiz1")
    quiz_id = _require_quiz_id(quiz_id)

    qs = QUESTIONS_BY_QUIZ[quiz_id]
    q = next((x for x in qs if x.get("id") == payload.id), None)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    question = q.get("question")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=500, detail="Invalid question in questions file")

    try:
        res = grade_answer(question=question, user_answer=payload.answer)

        stats = apply_answer_result(
            session_id=payload.session_id,
            qid=payload.id,
            answer=payload.answer,
            ok=bool(res.ok),
            feedback=str(res.feedback or ""),
        )

        return GradeOut(
            ok=res.ok,
            feedback=res.feedback,
            correct=stats.correct,
            answered=stats.answered,
            total=stats.total,
            pass_score=stats.pass_score,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        if DEBUG:
            raise HTTPException(status_code=500, detail=f"Grading failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Grading failed")


@app.post("/api/final_feedback", response_model=FinalFeedbackOut)
def final_feedback_api(payload: FinalFeedbackIn) -> FinalFeedbackOut:
    try:
        finish_session(payload.session_id)

        meta_s = get_session_meta(payload.session_id)
        if not meta_s:
            raise HTTPException(status_code=404, detail="Session not found")

        total = int(meta_s["total"])
        answered = int(meta_s["answered"])
        correct = int(meta_s["correct"])
        pass_score = int(meta_s["pass_score"])

        return final_feedback_safe(
            correct=correct,
            answered=answered,
            total=total,
            pass_score=pass_score,
        )
    except HTTPException:
        raise
    except Exception:
        return final_feedback_safe(
            correct=0,
            answered=0,
            total=1,
            pass_score=PASS_SCORE,
        )


@app.get("/api/leaderboard", response_model=LeaderboardOut)
def leaderboard_api(limit: int = 20) -> LeaderboardOut:
    try:
        items = leaderboard(limit=limit)
        return LeaderboardOut(items=items)
    except Exception as e:
        traceback.print_exc()
        if DEBUG:
            raise HTTPException(status_code=500, detail=f"Leaderboard failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Leaderboard failed")
