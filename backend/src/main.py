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

# --- Загружаем backend/.env, если он есть ---
try:
    from dotenv import load_dotenv  # type: ignore

    ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=ENV_PATH, override=False)
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = BASE_DIR / "questions.json"

PASS_SCORE = int(os.getenv("PASS_SCORE", "13"))


def load_questions() -> list[dict[str, Any]]:
    if not QUESTIONS_PATH.exists():
        raise RuntimeError(f"questions.json not found at: {QUESTIONS_PATH}")
    with QUESTIONS_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RuntimeError("questions.json must contain a JSON array")
    return data


QUESTIONS = load_questions()

app = FastAPI(title="AI Quiz Backend", version="0.6.0")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "y", "on"}


class QuestionOut(BaseModel):
    id: str
    question: str


class QuestionsListOut(BaseModel):
    questions: list[QuestionOut]
    total: int
    pass_score: int


class QuizMetaOut(BaseModel):
    total: int
    pass_score: int


class GradeIn(BaseModel):
    id: str = Field(..., description="ID вопроса из questions.json")
    answer: str = Field(..., min_length=1, description="Короткий ответ пользователя (суть)")


class FinalFeedbackIn(BaseModel):
    correct: int = Field(..., ge=0)
    answered: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=1)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/meta", response_model=QuizMetaOut)
def meta() -> QuizMetaOut:
    return QuizMetaOut(total=len(QUESTIONS), pass_score=PASS_SCORE)


@app.get("/api/questions", response_model=QuestionsListOut)
def list_questions() -> QuestionsListOut:
    out: list[QuestionOut] = []
    for q in QUESTIONS:
        qid = q.get("id")
        text = q.get("question")
        if isinstance(qid, str) and isinstance(text, str) and text.strip():
            out.append(QuestionOut(id=qid, question=text))
    return QuestionsListOut(questions=out, total=len(out), pass_score=PASS_SCORE)


@app.get("/api/questions/{question_id}", response_model=QuestionOut)
def get_question(question_id: str) -> QuestionOut:
    q = next((x for x in QUESTIONS if x.get("id") == question_id), None)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    question = q.get("question")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=500, detail="Invalid question in questions.json")

    return QuestionOut(id=question_id, question=question)


@app.post("/api/grade", response_model=GradeResult)
def grade(payload: GradeIn) -> GradeResult:
    q = next((x for x in QUESTIONS if x.get("id") == payload.id), None)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    question = q.get("question")
    if not isinstance(question, str) or not question.strip():
        raise HTTPException(status_code=500, detail="Invalid question in questions.json")

    try:
        return grade_answer(question=question, user_answer=payload.answer)
    except Exception as e:
        traceback.print_exc()
        if DEBUG:
            raise HTTPException(status_code=500, detail=f"Grading failed: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Grading failed")


@app.post("/api/final_feedback", response_model=FinalFeedbackOut)
def final_feedback_api(payload: FinalFeedbackIn) -> FinalFeedbackOut:
    # ВАЖНО: этот endpoint НЕ должен падать из-за LLM.
    server_total = len(QUESTIONS)

    total = server_total
    if payload.total is not None:
        # но сервер всё равно является источником истины
        total = server_total

    answered = payload.answered if payload.answered is not None else server_total
    correct = int(payload.correct)

    # Возвращаем всегда 200 с безопасным результатом
    return final_feedback_safe(
        correct=correct,
        answered=int(answered),
        total=int(total),
        pass_score=PASS_SCORE,
    )
