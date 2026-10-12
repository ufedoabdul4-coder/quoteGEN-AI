"""Per-request identity.

The HTTP layer resolves who is making the request (a Supabase user id) and
stores it here for the duration of the request. The storage layer reads it back
so every write and read is scoped to that user without threading a parameter
through every function signature.
"""

from __future__ import annotations

import contextvars

_current_user: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "quotegen_current_user", default=None
)


def set_current_user(user_id: str | None):
    """Set the active user id; returns a token for :func:`reset_current_user`."""
    return _current_user.set(user_id)


def reset_current_user(token) -> None:
    _current_user.reset(token)


def get_current_user() -> str | None:
    return _current_user.get()


def require_current_user() -> str:
    user_id = _current_user.get()
    if not user_id:
        raise RuntimeError("no authenticated user in context")
    return user_id
