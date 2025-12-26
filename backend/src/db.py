# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _default_db_path() -> Path:
    v = (os.getenv("QUIZ_DB_PATH") or "").strip()
    if v:
        return Path(v).expanduser().resolve()
    return (Path(__file__).resolve().parent / "quiz.db").resolve()


DB_PATH = _default_db_path()


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def init_db() -> None:
    """
    Создаёт схему. Если БД уже была — делает мягкую миграцию (добавляет колонки).
    """
    conn = _connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              nickname TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              user_id INTEGER NOT NULL,
              started_at TEXT NOT NULL DEFAULT (datetime('now')),
              finished_at TEXT,
              correct INTEGER NOT NULL DEFAULT 0,
              answered INTEGER NOT NULL DEFAULT 0,
              total INTEGER NOT NULL DEFAULT 0,
              pass_score INTEGER NOT NULL DEFAULT 0,
              last_activity_at TEXT NOT NULL DEFAULT (datetime('now')),
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS answers (
              session_id TEXT NOT NULL,
              qid TEXT NOT NULL,
              ok INTEGER NOT NULL, -- 0/1
              answer TEXT NOT NULL,
              feedback TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              PRIMARY KEY (session_id, qid),
              FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity_at);
            """
        )

        # --- миграции users (накопительный счёт) ---
        cols_u = _table_columns(conn, "users")
        if "total_correct" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN total_correct INTEGER NOT NULL DEFAULT 0;")
        if "total_answered" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN total_answered INTEGER NOT NULL DEFAULT 0;")
        if "attempts" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;")
        if "last_seen_at" not in cols_u:
            conn.execute("ALTER TABLE users ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT (datetime('now'));")

        # --- миграции sessions: quiz_id + is_public ---
        cols_s = _table_columns(conn, "sessions")
        if "quiz_id" not in cols_s:
            conn.execute("ALTER TABLE sessions ADD COLUMN quiz_id TEXT NOT NULL DEFAULT 'quiz1';")
        if "is_public" not in cols_s:
            conn.execute("ALTER TABLE sessions ADD COLUMN is_public INTEGER NOT NULL DEFAULT 1;")

        conn.commit()
    finally:
        conn.close()


def _norm_nickname(nickname: str) -> str:
    return " ".join((nickname or "").strip().split())


def _get_or_create_user(conn: sqlite3.Connection, nickname: str) -> int:
    nn = _norm_nickname(nickname)
    if not nn:
        raise ValueError("nickname is empty")

    row = conn.execute("SELECT id FROM users WHERE nickname = ?", (nn,)).fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute("INSERT INTO users(nickname) VALUES (?)", (nn,))
    return int(cur.lastrowid)


def _guest_nickname() -> str:
    # короткий, уникальный, без пробелов
    return f"guest-{uuid.uuid4().hex[:8]}"


def create_session(nickname: str | None, total: int, pass_score: int, quiz_id: str, is_public: bool) -> dict[str, Any]:
    """
    Создает новую попытку (сессию) для конкретного quiz_id.
    Если nickname не задан — создаём гостевой ник и принудительно is_public=false.
    Накопительные очки — в users и обновляются при /api/grade ТОЛЬКО если is_public=1.
    """
    qid = (quiz_id or "").strip() or "quiz1"

    nn = _norm_nickname(nickname or "")
    if not nn:
        nn = _guest_nickname()
        is_public = False  # гостя не показываем

    pub_int = 1 if is_public else 0

    conn = _connect()
    try:
        user_id = _get_or_create_user(conn, nn)
        sid = str(uuid.uuid4())

        conn.execute(
            """
            INSERT INTO sessions(id, user_id, total, pass_score, quiz_id, is_public)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (sid, user_id, int(total), int(pass_score), qid, pub_int),
        )

        # attempts++ считаем только публичные попытки (чтобы скрытые не светились статистикой)
        if pub_int == 1:
            conn.execute(
                """
                UPDATE users
                SET attempts = attempts + 1,
                    last_seen_at = datetime('now')
                WHERE id = ?
                """,
                (user_id,),
            )
        else:
            conn.execute(
                "UPDATE users SET last_seen_at = datetime('now') WHERE id = ?",
                (user_id,),
            )

        conn.commit()
        return {"session_id": sid, "nickname": nn, "quiz_id": qid, "is_public": bool(pub_int)}
    finally:
        conn.close()


def get_session_meta(session_id: str) -> Optional[dict[str, Any]]:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT s.id, s.correct, s.answered, s.total, s.pass_score, s.started_at, s.finished_at,
                   s.quiz_id, s.is_public,
                   u.nickname
            FROM sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.id = ?
            """,
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


@dataclass
class ApplyAnswerResult:
    correct: int
    answered: int
    total: int
    pass_score: int
    changed: bool


def apply_answer_result(
    session_id: str,
    qid: str,
    answer: str,
    ok: bool,
    feedback: str,
) -> ApplyAnswerResult:
    """
    1) Сохраняет ответ (answers) в рамках session_id + qid.
    2) Обновляет счетчики текущей сессии (sessions.correct/answered).
    3) Обновляет НАКОПИТЕЛЬНЫЕ счетчики пользователя (users.total_correct/total_answered)
       ТОЛЬКО если sessions.is_public = 1.

    Корректно обрабатывает:
    - первый ответ на вопрос в сессии => answered +1
    - переответ в той же сессии с изменением ok => correct +/-1
    """
    conn = _connect()
    try:
        s = conn.execute(
            "SELECT id, user_id, correct, answered, total, pass_score, is_public FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not s:
            raise ValueError("session not found")

        user_id = int(s["user_id"])
        session_correct = int(s["correct"])
        session_answered = int(s["answered"])
        is_public = int(s["is_public"]) == 1

        prev = conn.execute(
            "SELECT ok FROM answers WHERE session_id = ? AND qid = ?",
            (session_id, qid),
        ).fetchone()

        ok_int = 1 if ok else 0

        delta_answered = 0
        delta_correct = 0
        changed = False

        if prev is None:
            delta_answered = 1
            delta_correct = 1 if ok else 0
            changed = True

            conn.execute(
                """
                INSERT INTO answers(session_id, qid, ok, answer, feedback)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, qid, ok_int, answer, feedback),
            )
        else:
            prev_ok = int(prev["ok"])

            conn.execute(
                """
                UPDATE answers
                SET ok = ?, answer = ?, feedback = ?, updated_at = datetime('now')
                WHERE session_id = ? AND qid = ?
                """,
                (ok_int, answer, feedback, session_id, qid),
            )

            if prev_ok != ok_int:
                changed = True
                if prev_ok == 1 and ok_int == 0:
                    delta_correct = -1
                elif prev_ok == 0 and ok_int == 1:
                    delta_correct = 1

        session_answered = max(0, session_answered + delta_answered)
        session_correct = max(0, session_correct + delta_correct)

        conn.execute(
            """
            UPDATE sessions
            SET correct = ?, answered = ?, last_activity_at = datetime('now')
            WHERE id = ?
            """,
            (session_correct, session_answered, session_id),
        )

        # ✅ накопительные totals обновляем ТОЛЬКО для публичных сессий
        if is_public and (delta_answered != 0 or delta_correct != 0):
            conn.execute(
                """
                UPDATE users
                SET total_answered = MAX(0, total_answered + ?),
                    total_correct  = MAX(0, total_correct  + ?),
                    last_seen_at   = datetime('now')
                WHERE id = ?
                """,
                (int(delta_answered), int(delta_correct), user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET last_seen_at = datetime('now') WHERE id = ?",
                (user_id,),
            )

        conn.commit()

        return ApplyAnswerResult(
            correct=session_correct,
            answered=session_answered,
            total=int(s["total"]),
            pass_score=int(s["pass_score"]),
            changed=changed,
        )
    finally:
        conn.close()


def finish_session(session_id: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            UPDATE sessions
            SET finished_at = COALESCE(finished_at, datetime('now')),
                last_activity_at = datetime('now')
            WHERE id = ?
            """,
            (session_id,),
        )
        conn.commit()
    finally:
        conn.close()


def leaderboard(limit: int = 20) -> list[dict[str, Any]]:
    """
    Лидерборд по пользователю (nickname), накопительный.
    Т.к. totals обновляются только для публичных сессий,
    скрытые/гостевые прохождения сюда не попадут.

    Возвращаем поля, которые ждёт фронт:
      best_correct, best_answered, last_activity_at
    """
    lim = max(1, min(int(limit), 200))
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
              nickname,
              total_correct AS best_correct,
              total_answered AS best_answered,
              attempts,
              last_seen_at AS last_activity_at
            FROM users
            WHERE total_answered > 0 OR total_correct > 0 OR attempts > 0
            ORDER BY total_correct DESC, total_answered DESC, last_seen_at DESC
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
