"""Durable storage for documents, previews, reference designs and profile.

Everything lives under ``storage/`` at the repository root as plain files, so a
document can be inspected, backed up or deleted without a database. Records are
written atomically (temp file then replace) to avoid a half-written JSON file if
the process stops mid-save.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from models import BusinessProfile, DocumentRecord, Settings, TemplateMeta

ROOT = Path(__file__).resolve().parents[2]
STORAGE = ROOT / "storage"
DOCUMENTS = STORAGE / "documents"
PREVIEWS = STORAGE / "previews"
REFERENCES = STORAGE / "references"
PROFILE_FILE = STORAGE / "profile.json"
SETTINGS_FILE = STORAGE / "settings.json"

_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _ensure_dirs() -> None:
    for path in (STORAGE, DOCUMENTS, PREVIEWS, REFERENCES):
        path.mkdir(parents=True, exist_ok=True)


def _safe(document_id: str) -> str:
    if not _SAFE_ID.match(document_id or ""):
        raise ValueError(f"unsafe document id: {document_id!r}")
    return document_id


def new_id(prefix: str = "doc") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_bytes(data)
    last_error: OSError | None = None
    for attempt in range(12):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as exc:
            # Windows: the destination can be briefly locked by an antivirus or
            # indexer while it is being replaced. Retry with a short back-off.
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    with contextlib.suppress(OSError):
        tmp.unlink()
    if last_error is not None:
        raise last_error


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# documents
# ---------------------------------------------------------------------------


def _document_path(document_id: str) -> Path:
    return DOCUMENTS / f"{_safe(document_id)}.json"


def save_document(record: DocumentRecord) -> DocumentRecord:
    _ensure_dirs()
    record.updated_at = timestamp()
    if not record.created_at:
        record.created_at = record.updated_at
    _write_atomic(_document_path(record.id), record.model_dump_json(indent=2).encode("utf-8"))
    return record


def save_record(record: DocumentRecord) -> DocumentRecord:
    return save_document(record)


def get_document(document_id: str) -> DocumentRecord | None:
    payload = _read_json(_document_path(document_id))
    if payload is None:
        return None
    try:
        return DocumentRecord.model_validate(payload)
    except Exception:
        return None


def list_documents() -> list[DocumentRecord]:
    _ensure_dirs()
    records: list[DocumentRecord] = []
    for path in DOCUMENTS.glob("*.json"):
        payload = _read_json(path)
        if payload is None:
            continue
        try:
            records.append(DocumentRecord.model_validate(payload))
        except Exception:
            continue
    records.sort(key=lambda r: r.updated_at or r.created_at, reverse=True)
    return records


def delete_document(document_id: str) -> bool:
    document_id = _safe(document_id)
    removed = False
    for path in (_document_path(document_id),
                 PREVIEWS / f"{document_id}.pdf",
                 REFERENCES / f"{document_id}.pdf"):
        if path.exists():
            path.unlink()
            removed = True
    preview_dir = PREVIEWS / document_id
    if preview_dir.is_dir():
        for stale in preview_dir.glob("*.png"):
            stale.unlink()
        preview_dir.rmdir()
        removed = True
    return removed


# ---------------------------------------------------------------------------
# generated artefacts
# ---------------------------------------------------------------------------


def save_pdf(document_id: str, pdf_bytes: bytes) -> str:
    _ensure_dirs()
    _safe(document_id)
    _write_atomic(PREVIEWS / f"{document_id}.pdf", pdf_bytes)
    return f"/documents/{document_id}/pdf"


def save_previews(document_id: str, pages: list[bytes]) -> list[str]:
    _ensure_dirs()
    _safe(document_id)
    folder = PREVIEWS / document_id
    folder.mkdir(parents=True, exist_ok=True)
    urls: list[str] = []
    for index, png in enumerate(pages):
        name = f"page-{index + 1}.png"
        _write_atomic(folder / name, png)
        urls.append(f"/documents/{document_id}/preview/{index + 1}")
    return urls


def read_pdf(document_id: str) -> bytes | None:
    path = PREVIEWS / f"{_safe(document_id)}.pdf"
    return path.read_bytes() if path.exists() else None


def read_preview(document_id: str, page: int) -> bytes | None:
    path = PREVIEWS / _safe(document_id) / f"page-{page}.png"
    return path.read_bytes() if path.exists() else None


# ---------------------------------------------------------------------------
# reference designs
# ---------------------------------------------------------------------------


def save_reference(reference_id: str, pdf_bytes: bytes) -> None:
    _ensure_dirs()
    _write_atomic(REFERENCES / f"{_safe(reference_id)}.pdf", pdf_bytes)


def read_reference(reference_id: str) -> bytes | None:
    path = REFERENCES / f"{_safe(reference_id)}.pdf"
    return path.read_bytes() if path.exists() else None


def save_reference_meta(reference_id: str, meta: dict[str, Any]) -> None:
    _ensure_dirs()
    _write_atomic(REFERENCES / f"{_safe(reference_id)}.json",
                  json.dumps(meta, indent=2).encode("utf-8"))


def get_reference_meta(reference_id: str) -> dict[str, Any] | None:
    return _read_json(REFERENCES / f"{_safe(reference_id)}.json")


def list_references() -> list[dict[str, Any]]:
    _ensure_dirs()
    metas: list[dict[str, Any]] = []
    for path in REFERENCES.glob("*.json"):
        payload = _read_json(path)
        if payload and payload.get("kind") != "template":
            metas.append(payload)
    metas.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return metas


def delete_reference(reference_id: str) -> bool:
    reference_id = _safe(reference_id)
    removed = False
    for path in (REFERENCES / f"{reference_id}.pdf", REFERENCES / f"{reference_id}.json"):
        if path.exists():
            path.unlink()
            removed = True
    if load_settings().active_template_id == reference_id:
        save_settings(Settings(active_template_id=None))
    return removed


# ---------------------------------------------------------------------------
# master templates (stored alongside reference designs)
# ---------------------------------------------------------------------------


def save_template_meta(meta: TemplateMeta | dict[str, Any]) -> dict[str, Any]:
    _ensure_dirs()
    payload = meta.model_dump() if isinstance(meta, TemplateMeta) else meta
    _write_atomic(REFERENCES / f"{_safe(payload['id'])}.json",
                  json.dumps(payload, indent=2).encode("utf-8"))
    return payload


def get_template(template_id: str) -> TemplateMeta | None:
    payload = _read_json(REFERENCES / f"{_safe(template_id)}.json")
    if payload is None or payload.get("kind") != "template":
        return None
    try:
        return TemplateMeta.model_validate(payload)
    except Exception:
        return None


def list_templates() -> list[TemplateMeta]:
    _ensure_dirs()
    templates: list[TemplateMeta] = []
    active_id = get_active_template_id()
    for path in REFERENCES.glob("*.json"):
        payload = _read_json(path)
        if not payload or payload.get("kind") != "template":
            continue
        try:
            template = TemplateMeta.model_validate(payload)
        except Exception:
            continue
        template.is_active = template.id == active_id
        templates.append(template)
    templates.sort(key=lambda item: item.created_at, reverse=True)
    return templates


def rename_template(template_id: str, name: str) -> TemplateMeta | None:
    meta = get_template(template_id)
    if meta is None:
        return None
    meta.name = name.strip()
    meta.updated_at = timestamp()
    save_template_meta(meta)
    return meta


def delete_template(template_id: str) -> bool:
    template_id = _safe(template_id)
    removed = False
    for path in (REFERENCES / f"{template_id}.pdf", REFERENCES / f"{template_id}.json"):
        if path.exists():
            path.unlink()
            removed = True
    if get_active_template_id() == template_id:
        set_active_template_id(None)
    return removed


# ---------------------------------------------------------------------------
# settings (active master template)
# ---------------------------------------------------------------------------


def load_settings() -> Settings:
    payload = _read_json(SETTINGS_FILE)
    if payload is None:
        return Settings()
    try:
        return Settings.model_validate(payload)
    except Exception:
        return Settings()


def save_settings(settings: Settings) -> Settings:
    _ensure_dirs()
    _write_atomic(SETTINGS_FILE, settings.model_dump_json(indent=2).encode("utf-8"))
    return settings


def get_active_template_id() -> str | None:
    return load_settings().active_template_id


def set_active_template_id(template_id: str | None) -> Settings:
    if template_id is not None and get_template(template_id) is None:
        raise ValueError(f"unknown template: {template_id}")
    return save_settings(Settings(active_template_id=template_id))


# ---------------------------------------------------------------------------
# business profile
# ---------------------------------------------------------------------------


def load_profile() -> BusinessProfile:
    payload = _read_json(PROFILE_FILE)
    if payload is None:
        return BusinessProfile()
    try:
        return BusinessProfile.model_validate(payload)
    except Exception:
        return BusinessProfile()


def save_profile(profile: BusinessProfile) -> BusinessProfile:
    _ensure_dirs()
    _write_atomic(PROFILE_FILE, profile.model_dump_json(indent=2).encode("utf-8"))
    return profile


# ---------------------------------------------------------------------------
# backend selection
# ---------------------------------------------------------------------------
#
# When Supabase credentials are present the whole module is transparently
# rebound to the Supabase implementation so the rest of the app keeps calling
# ``store.*`` unchanged. Without credentials the local file backend above is
# used, which is what development and the test-suite rely on.


from services import supabase_client  # noqa: E402

_SUPABASE_FUNCTIONS = (
    "save_document",
    "save_record",
    "get_document",
    "list_documents",
    "delete_document",
    "save_pdf",
    "save_previews",
    "read_pdf",
    "read_preview",
    "save_reference",
    "read_reference",
    "save_reference_meta",
    "get_reference_meta",
    "list_references",
    "delete_reference",
    "save_template_meta",
    "get_template",
    "list_templates",
    "rename_template",
    "delete_template",
    "load_settings",
    "save_settings",
    "get_active_template_id",
    "set_active_template_id",
    "load_profile",
    "save_profile",
)


def using_supabase() -> bool:
    return supabase_client.is_enabled()


if using_supabase():
    from services import supabase_store as _supabase_store

    for _name in _SUPABASE_FUNCTIONS:
        globals()[_name] = getattr(_supabase_store, _name)
