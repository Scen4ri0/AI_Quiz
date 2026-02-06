# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from gigachat_client import get_llm


class GradeResult(BaseModel):
    """
    Tool schema for LLM structured output.
    GigaChat требует top-level description.
    """
    model_config = {
        "title": "GradeResult",
        "json_schema_extra": {
            "description": "Quiz grading result. Contains ok (boolean) and feedback (string)."
        },
    }

    ok: bool = Field(
        ...,
        description="True if the user's answer is correct in essence; иначе false."
    )
    feedback: str = Field(
        ...,
        description=(
            "If ok=false: ONE short hint without spoilers (friendly zoomer vibe + emojis). "
            "If ok=true: short explanation (friendly zoomer vibe + a few emojis). "
            "No slang dictionaries; slang is chosen freely by the assistant and must be natural."
        ),
    )


class FinalFeedbackOut(BaseModel):
    """
    Final feedback payload returned by backend (not a tool).
    """
    model_config = {
        "title": "FinalFeedbackOut",
        "json_schema_extra": {
            "description": "Final quiz feedback: passed flag and message text."
        },
    }

    passed: bool = Field(..., description="True if user passed the quiz, else false.")
    message: str = Field(..., description="Final feedback text (no toxicity, no profanity).")


_HINT_MAX_CHARS = 200

_PROFANITY_PATTERNS = [
    r"\bбля(дь|ть|ха|)\b",
    r"\bсука\b",
    r"\bхуй(ня|)\b",
    r"\bпизд(а|ец|)\b",
    r"\bеб(ать|ан|)\b",
    r"\bнахуй\b",
    r"\bзаеб\b",
]

# ✅ обновлено по твоему diff
_ZOOMER_TERMS: list[str] = [
    "Кринж", "Мид", "Топ", "Скам", "Сигма",
    "Норм",  "Фейл", "Лол",  "База", "Факт",
    "Душно", "Тильт", "Вайб", "Чил",
    "NPC", "Бот", "Фейк", "Рэд флаг", "Грин флаг",
    "Скуф",
    "Хайп",
    "Краш",
    "Луз", "Вин", "Тащить", "Скилл", "Нуб",
    "Это база", "Плюс реп",
    "Бумер", "Миллениал", "Зумер", "Альфа", "Бумерский прикол"
]


def _mask_profanity(text: str) -> str:
    out = text or ""
    for pat in _PROFANITY_PATTERNS:
        out = re.sub(pat, "—", out, flags=re.IGNORECASE)
    return out


def _sanitize_output(text: str, max_chars: int) -> str:
    t = re.sub(r"\s+", " ", (text or "")).strip()
    t = _mask_profanity(t)
    if len(t) > max_chars:
        t = t[:max_chars].rstrip()
    return t


def _extract_llm_content(resp: Any) -> str:
    """
    Универсально вытаскиваем текст из того, что вернул llm.invoke().
    Работает для LangChain-сообщений и для dict/прочих структур.
    """
    if resp is None:
        return ""
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                txt = item.get("text") or item.get("content") or ""
                if isinstance(txt, str) and txt.strip():
                    parts.append(txt)
        return "\n".join(parts).strip()
    if isinstance(resp, dict):
        c = resp.get("content")
        if isinstance(c, str):
            return c
    return str(resp).strip()


def _llm_text(prompt: str, max_chars: int = 800, tries: int = 2) -> str:
    """
    ✅ FIX: Ранее final_feedback_safe() вызывал _llm_text(), но её не было -> NameError.
    Тут делаем безопасный вызов LLM с несколькими попытками и нормализацией текста.
    """
    llm = get_llm()
    last_text = ""
    t = max(1, int(tries))

    for _ in range(t):
        try:
            resp = llm.invoke(prompt)
            text = _extract_llm_content(resp)
            text = _sanitize_output(text, max_chars)
            if text:
                return text
            last_text = text
        except Exception:
            # Не пробрасываем наружу — final_feedback_safe и так fallback-ит,
            # а /api/final_feedback не должен падать из-за LLM.
            continue

    return _sanitize_output(last_text, max_chars)


def _looks_like_definition_dump(text: str) -> bool:
    """
    Лёгкая эвристика: если модель начинает давать определение "X — это ..." на пол-экрана.
    Нам это особенно нельзя при ok=false.
    """
    s = (text or "").strip()
    if len(s) > 260:
        return True
    if re.search(r"—\s*это\s", s, flags=re.IGNORECASE) and len(s) > 180:
        return True
    return False


def _compact_hint(text: str) -> str:
    """
    Делает feedback для ok=false:
    - 1 предложение
    - без спойлеров
    - с вайбом (эмодзи + лёгкий сленг), но без лекции
    """
    t = _sanitize_output(text, 800)

    # Оставляем только первое предложение/фразу
    parts = re.split(r"(?<=[.!?])\s+|\s*[\n\r]+\s*", t, maxsplit=1)
    t = (parts[0] if parts else t).strip()

    # Если попахивает "лекцией" — превращаем в наводку-шаблон
    if _looks_like_definition_dump(t):
        t = "Чуть докрути: назови 1–2 ключевые штуки, которые тут важны, без деталей 😉"

    # Убираем жёсткое раскрытие "X — это ..." в наводке
    t = re.sub(
        r"^\s*([А-ЯA-ZЁ][^.!?]{0,60})\s*—\s*это\s+.*$",
        r"Наводка: уточни, что именно означает «\1» и зачем это важно 😌",
        t,
        flags=re.IGNORECASE,
    )

    # Финальные лимиты
    if len(t) > _HINT_MAX_CHARS:
        t = t[:_HINT_MAX_CHARS].rstrip()

    if len(t) < 30:
        t = "Наводка: уточни ключевую идею (1–2 мысли) — и будет топ ✨"

    # Немного вайба, если эмодзи вообще нет
    if not re.search(r"[\U0001F300-\U0001FAFF]", t):
        t = t.rstrip(".") + " 🙂"

    return t


def _make_grade_prompt(question: str, user_answer: str, strict: bool) -> str:
    strict_block = ""
    if strict:
        strict_block = """
СТРОГО:
- При ok=false: одно короткое предложение-наводка, без объяснения темы и без определения.
- При ok=true: не уходи в простыню; 4–8 предложений максимум.
- Не делай “словарь сленга” и не перечисляй термины списком.
""".strip()

    return f"""
Ты — дружелюбный проверяющий квиза по LLM. Стиль: лёгкий зумерский вайб, но по делу 😄

Важно:
- Сленг выбирай сам(а), естественно, без словарей и без “чеклистов”.
- Эмодзи: да, но умеренно.
- Никакой токсичности, грубости и мата.

Верни объект (только эти поля):
- ok: boolean
- feedback: string

Оценка:
- ok=true, если ответ по сути верный (даже если очень кратко).
- ok=false, если ключевой идеи нет или она неверна.

feedback правила:
1) Если ok=false:
   - ОДНО короткое предложение (до ~200 символов) — наводка без спойлеров.
   - Можно 1–2 эмодзи, можно 1 лёгкую зумерскую вставку (типа “топ/кринж/вайб/имба/душно”), но не перегибай.
2) Если ok=true:
   - 4–8 предложений: похвали, объясни чуть глубже и структурно.
   - Добавь 2–5 эмодзи за весь текст, и 1–2 лёгких зумерских словечка (естественно в тексте).
   - Не превращай в лекцию, держи темп и ясность.

{strict_block}

ВОПРОС:
{question}

ОТВЕТ ПОЛЬЗОВАТЕЛЯ (суть):
{user_answer}
""".strip()


def grade_answer(question: str, user_answer: str) -> GradeResult:
    llm = get_llm()
    last: GradeResult | None = None

    for attempt in range(2):
        strict = attempt == 1
        prompt = _make_grade_prompt(question, user_answer, strict=strict)

        structured_llm = llm.with_structured_output(GradeResult)
        result: GradeResult = structured_llm.invoke(prompt)
        last = result

        if result.ok is False:
            result.feedback = _compact_hint(result.feedback)
            # если вдруг модель всё равно сделала длинно — вторая попытка строгая
            if len(result.feedback) <= _HINT_MAX_CHARS:
                return result
            continue

        # ok=true: чуть подчистим, но не убиваем эмоции
        result.feedback = _mask_profanity(result.feedback).strip()
        # Не схлопываем все пробелы в один — иначе теряется “вайб”.
        result.feedback = re.sub(r"[ \t]+\n", "\n", result.feedback)
        result.feedback = _sanitize_output(result.feedback, 1400)

        return result

    # Фолбэк
    if last is None:
        return GradeResult(ok=False, feedback="Что-то пошло не так 😅 Попробуй ещё раз чуть позже.")
    if last.ok is False:
        last.feedback = _compact_hint(last.feedback)
    else:
        last.feedback = _sanitize_output(last.feedback, 1400)
    return last


def final_feedback_safe(correct: int, answered: int, total: int, pass_score: int) -> FinalFeedbackOut:
    total = max(1, int(total))
    answered = max(0, min(int(answered), total))
    correct = max(0, min(int(correct), total))
    pass_score = max(0, int(pass_score))

    passed = bool(correct >= pass_score)

    prompt = f"""
Ты — ведущий квиза по LLM. Стиль: дружелюбный зумерский вайб 😎✨ (без перебора).

Сделай итоговый отзыв (3–6 предложений):
- Укажи прогресс: answered/total и correct/total
- Укажи порог pass_score
- Скажи прошёл/не прошёл (по-доброму)
- Дай 2 общих направления “что подтянуть” (без спойлеров)
- Добавь 3–6 эмодзи
- Используй 1–2 лёгких сленговых слова естественно (например: “топ”, “вайб”, “имба”, “чуть душно”, “кринж” — по ситуации)
- Без списков/чеклистов/словарей

Данные:
total: {total}
answered: {answered}
correct: {correct}
pass_score: {pass_score}
passed: {str(passed).lower()}

Верни только текст (без JSON).
""".strip()

    msg = _llm_text(prompt, max_chars=800, tries=2)
    if not msg:
        msg = "Не получилось собрать итоговый фидбек 😅 Попробуй ещё раз."

    msg = _sanitize_output(msg, 800)
    return FinalFeedbackOut(passed=passed, message=msg)
