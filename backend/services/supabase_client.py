"""Supabase client factory.

A single service-role client is created lazily and reused. The client is only
available when the deployment is configured with Supabase credentials; when it
is not, :func:`is_enabled` returns ``False`` and the app falls back to local
file storage so development and tests keep working without a database.
"""

from __future__ import annotations

import os
import threading
from typing import Optional

_lock = threading.Lock()
_client = None
_initialised = False


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def project_url() -> str:
    return _env("SUPABASE_URL")


def service_key() -> str:
    return _env("SUPABASE_SERVICE_ROLE_KEY")


def is_enabled() -> bool:
    return bool(project_url() and service_key())


def get_client():
    """Return the shared service-role client, or ``None`` when unconfigured."""
    global _client, _initialised
    if not is_enabled():
        return None
    if _initialised:
        return _client
    with _lock:
        if _initialised:
            return _client
        from supabase import create_client  # imported lazily; optional dependency

        _client = create_client(project_url(), service_key())
        _initialised = True
    return _client


def reset() -> None:
    """Drop the cached client (used by tests when env changes)."""
    global _client, _initialised
    with _lock:
        _client = None
        _initialised = False


def verify_token(token: str) -> Optional[str]:
    """Return the user id for a Supabase access token, or ``None`` if invalid."""
    client = get_client()
    if client is None:
        return None
    try:
        result = client.auth.get_user(token)
    except Exception:
        return None
    user = getattr(result, "user", None)
    return getattr(user, "id", None)
