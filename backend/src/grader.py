# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any
from pydantic import BaseModel, Field

from gigachat_client import get_llm


class GradeResult(BaseModel):
    ok: bool = Field(..., description="Правильный ли ответ пользователя по сути (true/false)")
    feedback: str = Field(
        ...,
        description=(
            "Если ok=false — ОЧЕНЬ короткая наводка (без правильного ответа). "
            "Если ok=true — более развёрнутое корректное объяснение."
        ),
    )

    class Config:
        json_schema_extra = {"description": "Оценка ответа пользователя (ok/feedback)"}


class FinalFeedbackOut(BaseModel):
    passed: bool = Field(..., description="Прошёл ли пользователь тест (true/false)")
    message: str = Field(..., description="Итоговый отзыв (зумерский вайб), без мата/токсичности")


_HINT_MAX_CHARS = 180

_PROFANITY_PATTERNS = [
    r"\bбля(дь|ть|ха|)\b",
    r"\bсука\b",
    r"\bхуй(ня|)\b",
    r"\bпизд(а|ец|)\b",
    r"\bеб(ать|ан|)\b",
    r"\bнахуй\b",
    r"\bзаеб\b",
]


def _mask_profanity(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _PROFANITY_PATTERNS:
        out = re.sub(pat, "—", out, flags=re.IGNORECASE)
    return out


def _sanitize_output(text: str, max_chars: int) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    t = _mask_profanity(t)
    if len(t) > max_chars:
        t = t[:max_chars].rstrip()
    return t


_ZOOMER_STYLE_RULES = """
Пиши ОЧЕНЬ выраженно в стиле зумера по-русски: мемный вайб, уместный сленг, эмодзи.
Разрешено (по делу): “имба”, “кринж/не кринж”, “вайб”, “база/не база”, “сигма”, “изи”, “гг”.
Можно 1–2 мем-фразы: “ну это база”, “вот это имба”, “чуть кринжанул”, “gg, но не сдаёмся”.
Запрещено: мат, токсичность, унижение, оскорбления, дискриминация.
Тон: дружелюбный и поддерживающий, но яркий.
""".strip()


def _extract_llm_content(resp: Any) -> str:
    """
    Возвращает ТОЛЬКО текст ответа модели.
    Убирает обёртки типа AIMessage(content=..., additional_kwargs=..., response_metadata=...).
    """
    if resp is None:
        return ""

    # LangChain AIMessage / BaseMessage
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Иногда content бывает списком частей (dict/text)
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # встречается {"type": "...", "text": "..."} или похожие
                txt = item.get("text") or item.get("content") or ""
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt)
        return "\n".join(parts).strip()

    # Иногда могут вернуть dict
    if isinstance(resp, dict):
        c = resp.get("content")
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts = []
            for item in c:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    txt = item.get("text") or item.get("content") or ""
                    if isinstance(txt, str) and txt.strip():
                        parts.append(txt)
            return "\n".join(parts).strip()

    # Фолбэк — но он может включать мусор; лучше чем ничего
    return str(resp).strip()


def _llm_text(prompt: str, max_chars: int, tries: int = 2) -> str:
    """
    Пытается получить ТОЛЬКО текст от LLM. Делает несколько попыток.
    Ничего "готового" не подставляет — либо LLM-текст, либо пусто.
    """
    for _ in range(max(1, tries)):
        try:
            llm = get_llm()
            resp = llm.invoke(prompt)
            txt = _extract_llm_content(resp)
            txt = _sanitize_output(txt, max_chars)
            if txt:
                return txt
        except Exception:
            continue
    return ""


def _llm_hint_only(question: str, user_answer: str) -> str:
    prompt = f"""
Ты — ведущий квиза по ИИ.

{_ZOOMER_STYLE_RULES}

Нужно: дать ОДНУ очень короткую наводку (1 предложение, <= {_HINT_MAX_CHARS} символов).
ЗАПРЕЩЕНО:
- давать правильный ответ
- давать определение термина целиком
- перечислять пункты правильного ответа
- объяснять тему

Формат: “Чуть мимо — проверь ...”, “Не база: уточни ...”, “Плюс-минус, но добавь ...”.

ВОПРОС:
{question}

ОТВЕТ ПОЛЬЗОВАТЕЛЯ:
{user_answer}
""".strip()

    hint = _llm_text(prompt, max_chars=_HINT_MAX_CHARS, tries=2)
    if hint:
        cut_points = [". ", "; ", " — ", " - ", ":", ")", "!\u0020", "?\u0020", "\n"]
        for cp in cut_points:
            idx = hint.find(cp)
            if 0 < idx < 140:
                hint = hint[:idx].strip()
                break
        hint = _sanitize_output(hint, _HINT_MAX_CHARS)
    return hint


def _compact_hint_llm_first(question: str, user_answer: str, model_text: str) -> str:
    t = re.sub(r"\s+", " ", (model_text or "")).strip()

    cut_points = [". ", "; ", " — ", " - ", ":", ")", "!\u0020", "?\u0020", "\n"]
    for cp in cut_points:
        idx = t.find(cp)
        if 0 < idx < 140:
            t = t[:idx].strip()
            break

    t = _sanitize_output(t, _HINT_MAX_CHARS)

    if len(t) < 18:
        return _llm_hint_only(question, user_answer)

    return t


def grade_answer(question: str, user_answer: str) -> GradeResult:
    llm = get_llm()

    prompt = f"""
Ты — мемный, но строгий проверяющий квиза по LLM.

{_ZOOMER_STYLE_RULES}

Вход:
- ВОПРОС
- ОТВЕТ ПОЛЬЗОВАТЕЛЯ (коротко, “суть”)

Нужно вернуть объект:
- ok: boolean
- feedback: string

Критерии:
- ok=true, если ключевая идея верна, даже если ответ очень короткий.
- ok=false, если ключевой идеи нет или она неверна.

ОГРАНИЧЕНИЯ ДЛЯ feedback:
1) Если ok=false:
   - НИКАКИХ спойлеров и “правильного ответа”.
   - НЕ объясняй тему и НЕ давай определение термина.
   - Дай одну мемную, но полезную наводку (1 предложение, максимум 140–180 символов).
2) Если ok=true:
   - Дай корректное объяснение (4–8 предложений).
   - Очень зумер-вайб: сленг + 1–3 эмодзи + 1 мем-фраза (“ну это база/имба”).

ВОПРОС:
{question}

ОТВЕТ ПОЛЬЗОВАТЕЛЯ:
{user_answer}
""".strip()

    structured_llm = llm.with_structured_output(GradeResult)
    result: GradeResult = structured_llm.invoke(prompt)

    if result.ok is False:
        hint = _compact_hint_llm_first(question, user_answer, result.feedback)
        if not hint:
            result.feedback = "Не удалось получить подсказку от LLM сейчас. Попробуй ещё раз."
        else:
            result.feedback = hint
    else:
        fb = _sanitize_output(result.feedback, 1200)
        if not fb:
            result.feedback = "Не удалось получить объяснение от LLM сейчас. Попробуй ещё раз."
        else:
            result.feedback = fb

    return result


def final_feedback_safe(correct: int, answered: int, total: int, pass_score: int) -> FinalFeedbackOut:
    total = max(1, int(total))
    answered = max(0, min(int(answered), total))
    correct = max(0, min(int(correct), total))

    passed = bool(correct >= pass_score)

    prompt_main = f"""
Ты — ведущий квиза по ИИ в ультра-зумерском стиле.

{_ZOOMER_STYLE_RULES}

Сделай итоговый отзыв (3–6 предложений), ярко и мемно, но без мата/токсичности.
Обязательно:
- Укажи прогресс: answered/total и счёт correct/total
- Укажи порог pass_score
- Скажи прошёл/не прошёл (по-доброму)
- Дай 2 коротких “что подтянуть” (общими темами, без спойлеров правильных ответов)
- 2–4 эмодзи
- 1 мем-фраза уровня “база/имба/gg”, без перебора

НЕЛЬЗЯ:
- Спойлерить правильные ответы на вопросы
- Давать определения “как в учебнике” целиком
- Токсичить

Данные:
- total: {total}
- answered: {answered}
- correct: {correct}
- pass_score: {pass_score}
- passed: {str(passed).lower()}

Верни только текст (без JSON).
""".strip()

    prompt_backup = f"""
Сгенерируй короткий мемный отзыв в стиле зумера (2–4 предложения), без мата и токсичности.
Данные: correct={correct}, total={total}, answered={answered}, pass_score={pass_score}, passed={str(passed).lower()}.
Верни только текст.
""".strip()

    msg = _llm_text(prompt_main, max_chars=900, tries=2)
    if not msg:
        msg = _llm_text(prompt_backup, max_chars=500, tries=2)

    if not msg:
        msg = "Не удалось получить отзыв от LLM сейчас. Попробуй нажать «Завершить тест» ещё раз."

    return FinalFeedbackOut(passed=passed, message=msg)
