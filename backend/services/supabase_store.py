"""Supabase storage backend.

Mirrors the public surface of :mod:`services.store` but persists everything to
Supabase: documents, reference designs and master templates live in Postgres
tables (one row per user), while the binary artefacts (generated PDFs, preview
PNGs and uploaded master/reference PDFs) live in Storage buckets.

Every operation is scoped to the current user via :mod:`services.context`, so
two people using the hosted app never see each other's data.
"""

from __future__ import annotations

import os
import time
from typing import Any

from models import (
    BusinessProfile,
    DocumentRecord,
    Settings,
    TemplateMeta,
)

from services import supabase_client
from services.context import require_current_user

DOCUMENTS_BUCKET = "previews"
REFERENCES_BUCKET = "references"

DOCUMENTS_TABLE = "documents"
REFERENCES_TABLE = "references"
SETTINGS_TABLE = "settings"
PROFILES_TABLE = "profiles"

RETENTION_DAYS = int(os.environ.get("DOCUMENT_RETENTION_DAYS", "3"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _client():
    client = supabase_client.get_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    return client


def _bucket(name: str):
    return _client().storage.from_(name)


def _upload(name: str, path: str, data: bytes, content_type: str) -> None:
    _bucket(name).upload(
        path,
        data,
        {"content-type": content_type, "upsert": "true"},
    )


def _download(name: str, path: str) -> bytes | None:
    try:
        return _bucket(name).download(path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------


def save_document(record: DocumentRecord) -> DocumentRecord:
    user_id = require_current_user()
    record.updated_at = _now()
    if not record.created_at:
        record.created_at = record.updated_at
    _client().table(DOCUMENTS_TABLE).upsert(
        {
            "user_id": user_id,
            "id": record.id,
            "record": record.model_dump(mode="json"),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        }
    ).execute()
    return record


save_record = save_document


def get_document(document_id: str) -> DocumentRecord | None:
    user_id = require_current_user()
    result = (
        _client()
        .table(DOCUMENTS_TABLE)
        .select("record")
        .eq("user_id", user_id)
        .eq("id", document_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return None
    try:
        return DocumentRecord.model_validate(rows[0]["record"])
    except Exception:
        return None


def _age_days(stamp: str | None, now: float) -> float | None:
    if not stamp:
        return None
    try:
        created = time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))
    except ValueError:
        return None
    return (now - created) / 86400.0


def purge_expired_documents(max_age_days: int = RETENTION_DAYS) -> int:
    """Delete the current user's proposals older than ``max_age_days``."""
    user_id = require_current_user()
    try:
        result = (
            _client()
            .table(DOCUMENTS_TABLE)
            .select("id,created_at,updated_at")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception:
        return 0
    removed = 0
    now = time.time()
    for row in result.data or []:
        age = _age_days(row.get("created_at") or row.get("updated_at"), now)
        if age is not None and age >= max_age_days and delete_document(row.get("id")):
            removed += 1
    return removed


def list_documents() -> list[DocumentRecord]:
    user_id = require_current_user()
    purge_expired_documents()
    result = (
        _client()
        .table(DOCUMENTS_TABLE)
        .select("record")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )
    records: list[DocumentRecord] = []
    for row in result.data or []:
        try:
            records.append(DocumentRecord.model_validate(row["record"]))
        except Exception:
            continue
    return records


def delete_document(document_id: str) -> bool:
    user_id = require_current_user()
    result = (
        _client()
        .table(DOCUMENTS_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("id", document_id)
        .execute()
    )
    removed = bool(result.data)
    paths = [f"{user_id}/{document_id}.pdf"]
    try:
        pages = _bucket(DOCUMENTS_BUCKET).list(f"{user_id}/{document_id}")
        for entry in pages or []:
            name = entry.get("name") if isinstance(entry, dict) else None
            if name:
                paths.append(f"{user_id}/{document_id}/{name}")
    except Exception:
        pass
    try:
        _bucket(DOCUMENTS_BUCKET).remove(paths)
    except Exception:
        pass
    return removed


# ---------------------------------------------------------------------------
# generated artefacts
# ---------------------------------------------------------------------------


def save_pdf(document_id: str, pdf_bytes: bytes) -> str:
    user_id = require_current_user()
    _upload(DOCUMENTS_BUCKET, f"{user_id}/{document_id}.pdf", pdf_bytes, "application/pdf")
    return f"/documents/{document_id}/pdf"


def save_previews(document_id: str, pages: list[bytes]) -> list[str]:
    user_id = require_current_user()
    urls: list[str] = []
    for index, png in enumerate(pages):
        _upload(
            DOCUMENTS_BUCKET,
            f"{user_id}/{document_id}/page-{index + 1}.png",
            png,
            "image/png",
        )
        urls.append(f"/documents/{document_id}/preview/{index + 1}")
    return urls


def read_pdf(document_id: str) -> bytes | None:
    user_id = require_current_user()
    return _download(DOCUMENTS_BUCKET, f"{user_id}/{document_id}.pdf")


def read_preview(document_id: str, page: int) -> bytes | None:
    user_id = require_current_user()
    return _download(DOCUMENTS_BUCKET, f"{user_id}/{document_id}/page-{page}.png")


# ---------------------------------------------------------------------------
# references / templates
# ---------------------------------------------------------------------------


def save_reference(reference_id: str, pdf_bytes: bytes) -> None:
    user_id = require_current_user()
    _upload(REFERENCES_BUCKET, f"{user_id}/{reference_id}.pdf", pdf_bytes, "application/pdf")


def read_reference(reference_id: str) -> bytes | None:
    user_id = require_current_user()
    return _download(REFERENCES_BUCKET, f"{user_id}/{reference_id}.pdf")


def _upsert_meta(reference_id: str, meta: dict[str, Any], kind: str) -> None:
    user_id = require_current_user()
    meta = dict(meta)
    meta["id"] = reference_id
    meta["kind"] = kind
    _client().table(REFERENCES_TABLE).upsert(
        {
            "user_id": user_id,
            "id": reference_id,
            "kind": kind,
            "meta": meta,
            "created_at": meta.get("created_at") or _now(),
            "updated_at": _now(),
        }
    ).execute()


def save_reference_meta(reference_id: str, meta: dict[str, Any]) -> None:
    _upsert_meta(reference_id, meta, meta.get("kind", "reference"))


def get_reference_meta(reference_id: str) -> dict[str, Any] | None:
    user_id = require_current_user()
    result = (
        _client()
        .table(REFERENCES_TABLE)
        .select("meta")
        .eq("user_id", user_id)
        .eq("id", reference_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0]["meta"] if rows else None


def list_references() -> list[dict[str, Any]]:
    user_id = require_current_user()
    result = (
        _client()
        .table(REFERENCES_TABLE)
        .select("meta")
        .eq("user_id", user_id)
        .neq("kind", "template")
        .order("created_at", desc=True)
        .execute()
    )
    return [row["meta"] for row in result.data or []]


def delete_reference(reference_id: str) -> bool:
    user_id = require_current_user()
    result = (
        _client()
        .table(REFERENCES_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("id", reference_id)
        .execute()
    )
    removed = bool(result.data)
    try:
        _bucket(REFERENCES_BUCKET).remove([f"{user_id}/{reference_id}.pdf"])
    except Exception:
        pass
    if get_active_template_id() == reference_id:
        save_settings(Settings(active_template_id=None))
    return removed


def save_template_meta(meta: TemplateMeta | dict[str, Any]) -> dict[str, Any]:
    payload = meta.model_dump() if isinstance(meta, TemplateMeta) else dict(meta)
    _upsert_meta(payload["id"], payload, "template")
    return payload


def get_template(template_id: str) -> TemplateMeta | None:
    meta = get_reference_meta(template_id)
    if meta is None or meta.get("kind") != "template":
        return None
    try:
        return TemplateMeta.model_validate(meta)
    except Exception:
        return None


def list_templates() -> list[TemplateMeta]:
    user_id = require_current_user()
    result = (
        _client()
        .table(REFERENCES_TABLE)
        .select("meta")
        .eq("user_id", user_id)
        .eq("kind", "template")
        .order("created_at", desc=True)
        .execute()
    )
    active_id = get_active_template_id()
    templates: list[TemplateMeta] = []
    for row in result.data or []:
        try:
            template = TemplateMeta.model_validate(row["meta"])
        except Exception:
            continue
        template.is_active = template.id == active_id
        templates.append(template)
    return templates


def rename_template(template_id: str, name: str) -> TemplateMeta | None:
    meta = get_template(template_id)
    if meta is None:
        return None
    meta.name = name.strip()
    meta.updated_at = _now()
    save_template_meta(meta)
    return meta


def delete_template(template_id: str) -> bool:
    user_id = require_current_user()
    result = (
        _client()
        .table(REFERENCES_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("id", template_id)
        .execute()
    )
    removed = bool(result.data)
    try:
        _bucket(REFERENCES_BUCKET).remove([f"{user_id}/{template_id}.pdf"])
    except Exception:
        pass
    if get_active_template_id() == template_id:
        set_active_template_id(None)
    return removed


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    user_id = require_current_user()
    result = (
        _client()
        .table(SETTINGS_TABLE)
        .select("active_template_id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return Settings()
    return Settings(active_template_id=rows[0].get("active_template_id"))


def save_settings(settings: Settings) -> Settings:
    user_id = require_current_user()
    _client().table(SETTINGS_TABLE).upsert(
        {"user_id": user_id, "active_template_id": settings.active_template_id}
    ).execute()
    return settings


def get_active_template_id() -> str | None:
    return load_settings().active_template_id


def set_active_template_id(template_id: str | None) -> Settings:
    if template_id is not None and get_template(template_id) is None:
        raise ValueError(f"unknown template: {template_id}")
    return save_settings(Settings(active_template_id=template_id))


# ---------------------------------------------------------------------------
# profile
# ---------------------------------------------------------------------------


def load_profile() -> BusinessProfile:
    user_id = require_current_user()
    result = (
        _client()
        .table(PROFILES_TABLE)
        .select("data,business_type")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        return BusinessProfile()
    try:
        data = dict(rows[0]["data"])
        data["business_type"] = rows[0].get("business_type") or data.get("business_type", "")
        return BusinessProfile.model_validate(data)
    except Exception:
        return BusinessProfile()


def save_profile(profile: BusinessProfile) -> BusinessProfile:
    user_id = require_current_user()
    _client().table(PROFILES_TABLE).upsert(
        {
            "user_id": user_id,
            "business_type": profile.business_type,
            "data": profile.model_dump(mode="json"),
        }
    ).execute()
    return profile
