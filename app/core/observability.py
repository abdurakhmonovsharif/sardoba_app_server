import uuid
from contextlib import contextmanager
from contextvars import ContextVar


_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Return the current correlation id if present."""

    return _correlation_id.get()


def ensure_correlation_id(prefix: str | None = None) -> str:
    """Ensure a correlation id exists for the current context and return it."""

    existing = _correlation_id.get()
    if existing:
        return existing
    seed = prefix or "corr"
    generated = f"{seed}-{uuid.uuid4().hex[:12]}"
    _correlation_id.set(generated)
    return generated


@contextmanager
def correlation_context(correlation_id: str | None = None):
    """Context manager to temporarily set a correlation id."""

    token = _correlation_id.set(correlation_id or ensure_correlation_id())
    try:
        yield _correlation_id.get()
    finally:
        _correlation_id.reset(token)
