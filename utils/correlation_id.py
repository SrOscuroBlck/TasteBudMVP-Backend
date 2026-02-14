from contextvars import ContextVar
from typing import Optional
from uuid import uuid4

correlation_id_context: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str:
    correlation_id = correlation_id_context.get()
    if correlation_id is None:
        correlation_id = str(uuid4())
        correlation_id_context.set(correlation_id)
    return correlation_id


def set_correlation_id(correlation_id: str) -> None:
    correlation_id_context.set(correlation_id)


def clear_correlation_id() -> None:
    correlation_id_context.set(None)
