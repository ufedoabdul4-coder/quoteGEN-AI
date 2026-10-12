"""FastAPI application for quoteGEN.

The API is a thin shell over the services package: understanding, generation,
preview and reference analysis are all implemented in ``services/`` and this
module only moves bytes in and JSON out. That keeps the HTTP layer replaceable
and the engine testable without a server.
"""

from __future__ import annotations

import base64
import logging

import pymupdf
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

load_dotenv()

logger = logging.getLogger(__name__)

from models import (  # noqa: E402
    ActiveTemplateRequest,
    BusinessProfile,
    DocumentRecord,
    GenerateRequest,
    GenerateResponse,
    Settings,
    TemplateMeta,
    TemplateRenameRequest,
    UnderstandRequest,
    UnderstandResponse,
)
from services import ai, pipeline, reference, store  # noqa: E402
from services.designs import list_designs, to_design_info  # noqa: E402

app = FastAPI(
    title="quoteGEN API",
    description="AI quotation understanding, layout and rendering.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -- health & designs --------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok", "app": "quoteGEN", "version": "2.0.0"}


@app.get("/designs")
def get_designs():
    return {"designs": [to_design_info(d).model_dump() for d in list_designs()]}


# -- understanding -----------------------------------------------------------


@app.post("/understand")
async def understand(req: UnderstandRequest):
    understanding, used_ai, model, notes = await ai.understand(
        req.text, kind=req.kind, profile=req.profile, client=req.client, model=req.model
    )
    return UnderstandResponse(understanding=understanding, used_ai=used_ai,
                              model=model, notes=notes)


# -- rendering ---------------------------------------------------------------


def _load_reference_design(reference_id: str | None):
    if not reference_id:
        return None
    pdf = store.read_reference(reference_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="Reference design not found.")
    template = store.get_template(reference_id)
    meta = store.get_reference_meta(reference_id) or {}
    design = reference.analyze_reference(
        pdf,
        name=template.name if template else meta.get("name", "Reference design"),
        reference_of=reference_id,
    )
    if template:
        design.background_pdf = reference.prepare_template_background(
            pdf,
            content_top=design.content_area.top,
            content_bottom=design.content_area.bottom,
        )
    logger.debug(
        "Template id=%s filename=%s master_pages=%d background_pdf=%s",
        reference_id,
        (template.source_filename if template else meta.get("name", "Reference design")),
        _pdf_page_count(pdf),
        bool(design.background_pdf),
    )
    return design


def _render(req: GenerateRequest):
    req.reference_id = store.get_active_template_id() or req.reference_id
    design = _load_reference_design(req.reference_id)
    if req.understanding.failed or not req.understanding.blocks:
        reason = req.understanding.failure_reason or "No quotation content was understood."
        raise HTTPException(
            status_code=422,
            detail=f"Full quotation understanding failed: {reason}",
        )
    logger.debug(
        "Quotation replacement_mode=FULL_QUOTATION template_id=%s",
        req.reference_id or "none",
    )
    result = pipeline.build(
        req.design_id, req.understanding, req.profile, req.client,
        req.title, reference_design=design,
    )
    if design and design.background_pdf and logger.isEnabledFor(logging.DEBUG):
        master_pdf = store.read_reference(req.reference_id)
        supplied_text = " ".join([
            req.raw_input,
            req.understanding.title,
            req.understanding.subtitle,
            *(block.text for block in req.understanding.blocks),
            *(item for block in req.understanding.blocks for item in block.items),
            *(block.figure or "" for block in req.understanding.blocks),
        ])
        old_wording = (
            reference.old_master_wording_present(
                master_pdf, result[0].pdf_bytes, supplied_text,
            )
            if master_pdf else False
        )
        image_unchanged = (
            reference.background_image_matches(master_pdf, result[0].pdf_bytes)
            if master_pdf else False
        )
        logger.debug(
            "Template render id=%s output_pages=%d output_size_bytes=%d "
            "background_image_unchanged=%s old_master_wording_present=%s",
            req.reference_id, result[0].page_count, len(result[0].pdf_bytes),
            image_unchanged, old_wording,
        )
    return result


@app.post("/preview")
def preview(req: GenerateRequest):
    """Render an in-memory preview without saving a document."""
    result, report, previews = _render(req)
    return {
        "page_count": result.page_count,
        "previews": [_data_url(png) for png in previews],
        "validation": report.model_dump(),
    }


@app.post("/generate")
def generate(req: GenerateRequest):
    result, report, previews = _render(req)

    document_id = req.document_id or store.new_id("doc")
    pdf_url = store.save_pdf(document_id, result.pdf_bytes)
    preview_urls = store.save_previews(document_id, previews)

    record = store.get_document(document_id) or DocumentRecord(id=document_id)
    record.title = req.title or req.understanding.title or "Untitled quotation"
    record.design_id = req.design_id
    record.reference_id = req.reference_id or store.get_active_template_id()
    record.client = req.client
    record.profile = req.profile
    record.raw_input = req.raw_input
    record.input_kind = "paste"
    record.understanding = req.understanding
    record.validation = report
    record.pdf_url = pdf_url
    record.preview_url = preview_urls[0] if preview_urls else None
    record.page_count = result.page_count
    record.status = "ready" if report.ok else "needs_review"
    store.save_document(record)

    warnings = [f.message for f in report.findings if f.level in ("warning", "error")]
    return GenerateResponse(
        document_id=document_id, page_count=result.page_count, pdf_url=pdf_url,
        preview_urls=preview_urls, validation=report, warnings=warnings,
    )


# -- documents ---------------------------------------------------------------


@app.get("/documents")
def list_documents():
    return {"documents": [_summary(r) for r in store.list_documents()]}


@app.get("/documents/{document_id}")
def get_document(document_id: str):
    record = store.get_document(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return record.model_dump()


@app.delete("/documents/{document_id}")
def delete_document(document_id: str):
    return {"deleted": store.delete_document(document_id)}


@app.get("/documents/{document_id}/pdf")
def document_pdf(document_id: str):
    pdf = store.read_pdf(document_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found.")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{document_id}.pdf"'})


@app.get("/documents/{document_id}/preview/{page}")
def document_preview(document_id: str, page: int):
    png = store.read_preview(document_id, page)
    if png is None:
        raise HTTPException(status_code=404, detail="Preview not found.")
    return Response(content=png, media_type="image/png")


# -- reference designs -------------------------------------------------------


@app.post("/references/upload")
async def upload_reference(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF reference documents are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file was empty.")
    try:
        design = reference.analyze_reference(data, name=file.filename or "Reference design")
        page_count = _pdf_page_count(data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read that PDF: {exc}") from exc

    reference_id = store.new_id("ref")
    store.save_reference(reference_id, data)
    info = to_design_info(design)
    meta = {"id": reference_id, "name": file.filename or "Reference design",
            "created_at": store.timestamp(), "page_size": "US Letter",
            "size_bytes": len(data),
            "page_count": page_count,
            "status": "ready",
            "design": info.model_dump()}
    store.save_reference_meta(reference_id, meta)
    return meta


@app.get("/references")
def list_references():
    return {"references": store.list_references()}


@app.get("/references/{reference_id}/pdf")
def reference_pdf(reference_id: str):
    pdf = store.read_reference(reference_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="Reference not found.")
    return Response(content=pdf, media_type="application/pdf")


@app.delete("/references/{reference_id}")
def delete_reference(reference_id: str):
    return {"deleted": store.delete_reference(reference_id)}


# -- master templates --------------------------------------------------------


@app.get("/templates/active")
def get_active_template():
    template_id = store.get_active_template_id()
    if not template_id:
        templates = store.list_templates()
        template_id = next((item.id for item in templates if item.status == "ready"), None)
        if template_id:
            store.set_active_template_id(template_id)
    template = store.get_template(template_id) if template_id else None
    if template:
        template.is_active = True
    return {"template": template}


@app.post("/templates/active")
@app.put("/templates/active")
def set_active_template(req: ActiveTemplateRequest):
    if req.template_id is None:
        raise HTTPException(status_code=400, detail="template_id is required; use DELETE to clear.")
    try:
        store.set_active_template_id(req.template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Template not found.") from exc
    template = store.get_template(req.template_id)
    if template:
        template.is_active = True
    return {"template": template}


@app.delete("/templates/active")
def clear_active_template():
    store.set_active_template_id(None)
    return {"template": None}


@app.post("/templates/upload")
async def upload_template(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF templates are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file was empty.")
    try:
        page_count = _pdf_page_count(data)
        if page_count < 1:
            raise ValueError("The PDF contains no pages.")
        design = reference.analyze_reference(data, name=file.filename or "Master template")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read that PDF: {exc}") from exc

    template = TemplateMeta(
        id=store.new_id("tpl"),
        name=file.filename or "Master template",
        source_filename=file.filename or "",
        size_bytes=len(data),
        page_count=page_count,
        status="ready",
        created_at=store.timestamp(),
        design=to_design_info(design),
    )
    store.save_reference(template.id, data)
    store.save_template_meta(template)
    store.set_active_template_id(template.id)
    template.is_active = True
    return template.model_dump()


@app.put("/templates/{template_id}/replace")
async def replace_template(template_id: str, file: UploadFile = File(...)):
    template = store.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF templates are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded file was empty.")
    try:
        page_count = _pdf_page_count(data)
        if page_count < 1:
            raise ValueError("The PDF contains no pages.")
        design = reference.analyze_reference(data, name=file.filename or template.name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read that PDF: {exc}") from exc

    store.save_reference(template_id, data)
    template.source_filename = file.filename or template.source_filename
    template.size_bytes = len(data)
    template.page_count = page_count
    template.status = "ready"
    template.error = ""
    template.design = to_design_info(design)
    template.updated_at = store.timestamp()
    store.set_active_template_id(template_id)
    template.is_active = True
    store.save_template_meta(template)
    return template.model_dump()


@app.get("/templates")
def list_templates():
    return {"templates": [item.model_dump() for item in store.list_templates()]}


@app.get("/templates/{template_id}/pdf")
def template_pdf(template_id: str):
    if store.get_template(template_id) is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    pdf = store.read_reference(template_id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="Template PDF not found.")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{template_id}.pdf"'})


@app.get("/templates/{template_id}")
def get_template(template_id: str):
    template = store.get_template(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    template.is_active = template.id == store.get_active_template_id()
    return template.model_dump()


@app.patch("/templates/{template_id}")
@app.post("/templates/{template_id}/rename")
def rename_template(template_id: str, req: TemplateRenameRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Template name cannot be empty.")
    template = store.rename_template(template_id, name)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    template.is_active = template.id == store.get_active_template_id()
    return template.model_dump()


@app.delete("/templates/{template_id}")
def delete_template(template_id: str):
    if store.get_template(template_id) is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    return {"deleted": store.delete_template(template_id)}


# -- business profile --------------------------------------------------------


@app.get("/profile")
def get_profile():
    return store.load_profile().model_dump()


@app.put("/profile")
def update_profile(profile: BusinessProfile):
    return store.save_profile(profile).model_dump()


# -- helpers -----------------------------------------------------------------


def _summary(record: DocumentRecord) -> dict:
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status,
        "client": record.client.name,
        "page_count": record.page_count,
        "design_id": record.design_id,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
        "pdf_url": record.pdf_url,
        "preview_url": record.preview_url,
    }


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _pdf_page_count(data: bytes) -> int:
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return document.page_count


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
