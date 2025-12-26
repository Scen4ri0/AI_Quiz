# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field

from gigachat_client import get_llm


class GradeResult(BaseModel):
    """
    Tool schema for LLM structured output: MUST have top-level description.
    """
    model_config = {
        "title": "GradeResult",
        "json_schema_extra": {
            "description": "Quiz grading result. Contains ok (boolean) and feedback (string)."
        },
    }

    ok: bool = Field(..., description="True if the user's answer is correct in essence; иначе false.")
    feedback: str = Field(
        ...,
        description=(
            "If ok=false: one very short hint without spoilers. "
            "If ok=true: short explanation with appropriate slang."
        ),
    )


class FinalFeedbackOut(BaseModel):
    """
    Final feedback payload returned by backend. (Not a tool, but keep schema clean.)
    """
    model_config = {
        "title": "FinalFeedbackOut",
        "json_schema_extra": {
            "description": "Final quiz feedback: passed flag and message text."
        },
    }

    passed: bool = Field(..., description="True if user passed the quiz, else false.")
    message: str = Field(..., description="Final feedback text (no toxicity, no profanity).")


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

_ZOOMER_TERMS: list[str] = [
    "Кринж", "Лютый кринж", "Имба", "Мид", "Топ", "Скам", "Сигма",
    "Норм", "нормис", "Фейл", "Лол", "ор", "Жиза", "База", "Факт", "Рил", "Не рил",
    "Душно", "Душнила", "Тильт", "Вайб", "Нет вайба", "Чил", "Чиллово",
    "NPC", "Бот", "Фейк","Рэд флаг", "Грин флаг",
    "Сой", "Чад", "Скуф",
    "Залетело", "Флоп", "Флексить", "Заскамить", "Забайтить", 
    "Хайп", "Хайпануть", "Ливнуть", 
    "Ризз", "Нет ризза","Краш", "Крашнуться",
    "Луз", "Вин", "Тащить", "Скилл", "Нуб", "Баф", "Нерф", "Мета", "АФК",
    "Это база", "Словил вайб", "Минус вайб", "Я в тильте", "Плюс реп", "Минус карма",
    "Чисто по фану", "По приколу", "Не шарю", "Шаришь?", "Скилл ишью",
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


def _llm_text(prompt: str, max_chars: int, tries: int = 2) -> str:
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


def _stable_pick_terms(seed: str, k: int = 14) -> list[str]:
    base = [t for t in _ZOOMER_TERMS if isinstance(t, str) and t.strip()]
    if not base:
        return []
    k = max(6, min(int(k), 20))

    h = hashlib.sha256(seed.encode("utf-8")).digest()
    start = int.from_bytes(h[:4], "big") % len(base)

    out: list[str] = []
    i = 0
    while len(out) < k and i < len(base) * 2:
        idx = (start + i * 7) % len(base)
        term = base[idx]
        if term not in out:
            out.append(term)
        i += 1
    return out


def _count_terms_used(text: str, pool: list[str]) -> int:
    t_low = (text or "").lower()
    used = 0
    for term in pool:
        if term and term.lower() in t_low:
            used += 1
    return used


def _looks_like_list_dump(text: str) -> bool:
    s = text or ""
    low = s.lower()
    if "чеклист" in low or "словар" in low:
        return True
    if " | " in s:
        return True
    if s.count(",") >= 12 or s.count(";") >= 10:
        return True
    if re.search(r"\b(термины|список)\s*:\s*", s, flags=re.IGNORECASE):
        return True
    return False


def _style_rules_with_pool(pool: list[str]) -> str:
    return f"""
Пиши по-русски, в зумерском стиле, но по делу.

КРИТИЧНО:
- Встрой в текст 2–5 терминов/фраз ИЗ ЭТОГО ПУЛА (выбирай уместно по смыслу):
{", ".join(pool)}

НЕЛЬЗЯ:
- выводить пул/список/словарик/чеклист
- перечислять термины “через запятые/палочки” ради галочки
- писать “термины:” / “СЛЕНГ-...”
- мат, токсичность, унижение

Правило естественности:
термины должны быть частью предложений, а не отдельной строкой-списком.
""".strip()


def _make_grade_prompt(question: str, user_answer: str, pool: list[str], strict: bool) -> str:
    extra = ""
    if strict:
        extra = """
СТРОГО:
- если не вставишь 2–5 терминов из пула внутри обычных предложений — переформулируй
- никаких списков/чеклистов/перечней
""".strip()

    return f"""
Ты — мемный, но строгий проверяющий квиза по ИИ.

{_style_rules_with_pool(pool)}

{extra}

Нужно вернуть объект:
- ok: boolean
- feedback: string

Критерии:
- ok=true, если ключевая идея верна.
- ok=false, если ключевой идеи нет/она неверна.

Ограничения для feedback:
1) Если ok=false:
   - ОДНА короткая наводка (1 предложение, максимум 140–180 символов)
   - без спойлеров правильного ответа
   - используй 1–2 термина из пула или подобный зумерский сленг уместно
2) Если ok=true:
   - 4–8 предложений
   - объясни суть корректно
   - используй 2–5 терминов из пула уместно
   - 1–3 эмодзи

ВОПРОС:
{question}

ОТВЕТ ПОЛЬЗОВАТЕЛЯ:
{user_answer}
""".strip()


def grade_answer(question: str, user_answer: str) -> GradeResult:
    pool = _stable_pick_terms(seed=question + "\n" + user_answer, k=14)
    llm = get_llm()

    for attempt in range(2):
        strict = attempt == 1
        prompt = _make_grade_prompt(question, user_answer, pool, strict=strict)

        structured_llm = llm.with_structured_output(GradeResult)
        result: GradeResult = structured_llm.invoke(prompt)

        if result.ok is False:
            result.feedback = _sanitize_output(result.feedback, _HINT_MAX_CHARS)
        else:
            result.feedback = _sanitize_output(result.feedback, 1200)

        # Валидируем: не “чеклист” и реально использованы термины из пула
        if not _looks_like_list_dump(result.feedback):
            need = 2 if result.ok else 1
            used = _count_terms_used(result.feedback, pool)
            if used >= need:
                return result

    # Фолбэк: чистим явные разделители “листинга”
    result.feedback = re.sub(r"\s*\|\s*", " ", result.feedback).strip()
    result.feedback = _sanitize_output(result.feedback, 1200 if result.ok else _HINT_MAX_CHARS)
    return result


def final_feedback_safe(correct: int, answered: int, total: int, pass_score: int) -> FinalFeedbackOut:
    total = max(1, int(total))
    answered = max(0, min(int(answered), total))
    correct = max(0, min(int(correct), total))
    pass_score = max(0, int(pass_score))

    passed = bool(correct >= pass_score)

    seed = f"{correct}/{answered}/{total}/{pass_score}/{passed}"
    pool = _stable_pick_terms(seed=seed, k=14)

    prompt = f"""
Ты — ведущий квиза по ИИ.

{_style_rules_with_pool(pool)}

Сделай итоговый отзыв (3–6 предложений):
- Укажи прогресс: answered/total и correct/total
- Укажи порог pass_score
- Скажи прошёл/не прошёл (по-доброму)
- Дай 2 коротких “что подтянуть” (общими темами, без спойлеров)
- Используй 2–5 терминов из пула уместно
- 2–4 эмодзи
- 1 мемная фраза (встроенная в текст, не списком)

Данные:
total: {total}
answered: {answered}
correct: {correct}
pass_score: {pass_score}
passed: {str(passed).lower()}

Верни только текст (без JSON).
""".strip()

    msg = _llm_text(prompt, max_chars=900, tries=2)
    if not msg:
        msg = "Не удалось получить отзыв от LLM сейчас. Попробуй нажать «Завершить тест» ещё раз."

    # Если вдруг стало похоже на “список”, делаем один строгий репромпт
    if _looks_like_list_dump(msg) or _count_terms_used(msg, pool) < 2:
        prompt2 = f"""
Ты — ведущий квиза по ИИ.

{_style_rules_with_pool(pool)}

СТРОГО:
- никакого списка/чеклиста/перечня
- 2–5 терминов из пула внутри обычных предложений

Сделай отзыв 3–5 предложений по данным:
correct={correct}, answered={answered}, total={total}, pass_score={pass_score}, passed={str(passed).lower()}.
Верни только текст.
""".strip()
        msg2 = _llm_text(prompt2, max_chars=800, tries=1)
        if msg2:
            msg = msg2

    msg = _sanitize_output(msg, 900)
    return FinalFeedbackOut(passed=passed, message=msg)
