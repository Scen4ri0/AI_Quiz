# -*- coding: utf-8 -*-
import os

from langchain_gigachat import GigaChat


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_llm() -> GigaChat:
    credentials = os.getenv("GIGACHAT_CREDENTIALS")
    if not credentials:
        raise RuntimeError(
            "GIGACHAT_CREDENTIALS is not set. "
            "Set it in environment or backend/.env"
        )

    model = os.getenv("GIGACHAT_MODEL", "GigaChat-Pro")
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    temperature = float(os.getenv("GIGACHAT_TEMPERATURE", "0.0"))
    verify_ssl_certs = _to_bool(
        os.getenv("GIGACHAT_VERIFY_SSL_CERTS"), default=False
    )

    return GigaChat(
        credentials=credentials,
        scope=scope,
        model=model,
        temperature=temperature,
        verify_ssl_certs=verify_ssl_certs,
    )
