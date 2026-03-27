"""Page routes — HTML responses rendered via Jinja2."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ace.app import HtmxRedirect, get_db
from ace.models.annotation import get_annotation_counts_by_source, get_annotations_for_source
from ace.models.assignment import add_assignment, get_assignments_for_coder
from ace.models.codebook import list_codes
from ace.models.project import get_project
from ace.models.source import get_source_content, list_sources
from ace.services.coding_render import render_annotated_text

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "landing.html")


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        project = get_project(conn)
        sources = list_sources(conn)
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "project_name": project["name"],
            "source_count": len(sources),
        },
    )


def _coding_context(conn: sqlite3.Connection, coder_id: str, current_index: int) -> dict:
    """Assemble all data needed to render the coding page."""
    project = get_project(conn)
    sources = list_sources(conn)
    total_sources = len(sources)

    # Auto-create assignments if none exist for this coder
    assignments = get_assignments_for_coder(conn, coder_id)
    if not assignments:
        for source in sources:
            add_assignment(conn, source["id"], coder_id)
        assignments = get_assignments_for_coder(conn, coder_id)

    # Clamp index
    if current_index < 0:
        current_index = 0
    if current_index >= total_sources:
        current_index = total_sources - 1

    # Current source + content
    current_source = None
    source_text = ""
    current_status = "pending"
    if assignments and current_index < len(assignments):
        assignment = assignments[current_index]
        source_id = assignment["source_id"]
        current_source = {"display_id": assignment["display_id"], "id": source_id}
        current_status = assignment["status"]
        content_row = get_source_content(conn, source_id)
        if content_row:
            source_text = content_row["content_text"]
    elif sources:
        current_source = {"display_id": sources[current_index]["display_id"], "id": sources[current_index]["id"]}
        content_row = get_source_content(conn, sources[current_index]["id"])
        if content_row:
            source_text = content_row["content_text"]

    # Codes
    codes = list_codes(conn)
    codes_by_id = {c["id"]: dict(c) for c in codes}

    # Annotations for current source
    annotations = []
    if current_source:
        annotations = get_annotations_for_source(conn, current_source["id"], coder_id)

    # Annotation counts by source (for grid)
    annotation_counts = get_annotation_counts_by_source(conn, coder_id)

    # Annotated HTML
    annotated_html = render_annotated_text(source_text, annotations, codes_by_id)

    # Per-code frequency counts for current source
    code_counts: dict[str, int] = {}
    for ann in annotations:
        cid = ann["code_id"]
        code_counts[cid] = code_counts.get(cid, 0) + 1

    # Completion stats
    complete_count = sum(1 for a in assignments if a["status"] == "complete")
    complete_pct = round(complete_count / total_sources * 100) if total_sources > 0 else 0

    # Coder name
    coder_row = conn.execute("SELECT name FROM coder WHERE id = ?", (coder_id,)).fetchone()
    coder_name = coder_row["name"] if coder_row else "Unknown"

    return {
        "project_name": project["name"],
        "current_index": current_index,
        "total_sources": total_sources,
        "current_source": current_source,
        "current_status": current_status,
        "source_text": source_text,
        "codes": [dict(c) for c in codes],
        "codes_by_id": codes_by_id,
        "annotations": [dict(a) for a in annotations],
        "annotation_counts": annotation_counts,
        "annotated_html": annotated_html,
        "code_counts": code_counts,
        "complete_count": complete_count,
        "complete_pct": complete_pct,
        "coder_name": coder_name,
        "assignments": [dict(a) for a in assignments],
    }


@router.get("/code", response_class=HTMLResponse)
async def coding_page(request: Request, index: int = Query(default=0)):
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    coder_id: str | None = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        sources = list_sources(conn)
        if not sources:
            raise HtmxRedirect("/import")

        context = _coding_context(conn, coder_id, index)
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "coding.html", context)
