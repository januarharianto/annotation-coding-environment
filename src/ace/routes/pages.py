"""Page routes — HTML responses rendered via Jinja2."""

import html
import json
import sqlite3
from pathlib import Path

from markupsafe import Markup

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ace import __version__
from ace.app import HtmxRedirect, get_db
from ace.models.annotation import get_annotation_counts_by_source, get_annotations_for_source, get_code_view_data
from ace.models.assignment import add_assignment, get_assignments_for_coder
from ace.models.codebook import list_codes
from ace.models.project import get_project
from ace.models.source import get_source_content, list_sources
from ace.models.source_note import get_note, source_ids_with_notes

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


def _coding_context(
    conn: sqlite3.Connection,
    coder_id: str,
    current_index: int,
    project_path: str | None = None,
) -> dict:
    """Assemble all data needed to render the coding page."""
    from ace.services.coding_render import render_sentence_text
    from ace.services.text_splitter import split_into_units

    project = get_project(conn)
    sources = list_sources(conn)
    total_sources = len(sources)
    project_file_stem = Path(project_path).stem if project_path else ""

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
        current_source = {
            "display_id": sources[current_index]["display_id"],
            "id": sources[current_index]["id"],
        }
        content_row = get_source_content(conn, sources[current_index]["id"])
        if content_row:
            source_text = content_row["content_text"]

    # Source note state for the current source + presence set for the grid
    current_note_text = ""
    if current_source:
        current_note_text = get_note(conn, current_source["id"], coder_id) or ""
    notes_present = source_ids_with_notes(conn, coder_id)

    # Codes
    codes = list_codes(conn)
    codes_list = [dict(c) for c in codes]
    codes_by_id = {c["id"]: c for c in codes_list}

    # Annotations for current source
    annotations = []
    if current_source:
        annotations = get_annotations_for_source(conn, current_source["id"], coder_id)
    annotations_list = [dict(a) for a in annotations]

    # Annotation counts by source (for grid)
    annotation_counts = get_annotation_counts_by_source(conn, coder_id)

    # --- New: sentence-based rendering ---
    sentence_units = split_into_units(source_text)
    sentence_html = render_sentence_text(sentence_units, annotations_list, codes_by_id)

    # --- Grouped codes for sidebar ---
    group_dict: dict[str, list[dict]] = {}
    ungrouped_codes: list[dict] = []
    for code in codes_list:
        gn = code.get("group_name")
        if gn:
            group_dict.setdefault(gn, []).append(code)
        else:
            ungrouped_codes.append(code)
    grouped_codes = sorted(
        group_dict.items(),
        key=lambda x: min(c.get("sort_order", 0) for c in x[1]),
    )

    # Deduplicated codes applied to this source (for bottom code bar)
    seen_codes: set[str] = set()
    margin_codes: list[dict] = []
    for ann in annotations_list:
        cid = ann["code_id"]
        if cid not in seen_codes:
            code = codes_by_id.get(cid)
            if code:
                seen_codes.add(cid)
                margin_codes.append({
                    "code_id": cid,
                    "code_name": code["name"],
                    "colour": code["colour"],
                })

    # Per-code frequency counts for current source
    code_counts: dict[str, int] = {}
    for ann in annotations_list:
        cid = ann["code_id"]
        code_counts[cid] = code_counts.get(cid, 0) + 1

    # Annotation data for the SVG overlay (client-side rendering via _paintSvg).
    # Only id/code_id/start/end — colour comes from rect.ace-hl-{cid} CSS rules.
    annotation_highlights_json = Markup(html.escape(json.dumps([
        {"id": ann["id"], "code_id": ann["code_id"],
         "start": ann["start_offset"], "end": ann["end_offset"]}
        for ann in annotations_list
        if ann["code_id"] in codes_by_id
    ])))

    # Coder name
    coder_row = conn.execute(
        "SELECT name FROM coder WHERE id = ?", (coder_id,),
    ).fetchone()
    coder_name = coder_row["name"] if coder_row else "Unknown"

    # Flat per-source data for the client-rendered sparkline + tile grid.
    sources_json = [
        {
            "index": i,
            "source_id": a["source_id"],
            "display_id": a["display_id"],
            "count": annotation_counts.get(a["source_id"], 0),
            "flagged": a["status"] == "flagged",
            "note": a["source_id"] in notes_present,
        }
        for i, a in enumerate(assignments)
    ]

    return {
        "project_name": project["name"],
        "project_file_stem": project_file_stem,
        "current_index": current_index,
        "total_sources": total_sources,
        "current_source": current_source,
        "current_status": current_status,
        "source_text": source_text,
        "codes": codes_list,
        "codes_by_id": codes_by_id,
        "annotations": annotations_list,
        "annotation_counts": annotation_counts,
        "code_counts": code_counts,
        "coder_name": coder_name,
        "current_note_text": current_note_text,
        "has_note": bool(current_note_text),
        "source_ids_with_notes": notes_present,
        "assignments": [dict(a) for a in assignments],
        "sources_json": sources_json,
        "sentence_html": sentence_html,
        "grouped_codes": grouped_codes,
        "ungrouped_codes": ungrouped_codes,
        "margin_codes": margin_codes,
        "annotation_highlights_json": annotation_highlights_json,
        "version": __version__,
    }


@router.get("/agreement", response_class=HTMLResponse)
async def agreement_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "agreement.html")


@router.get("/code", response_class=HTMLResponse)
async def coding_page(
    request: Request,
    index: int = Query(default=0),
    open_path: str | None = Query(default=None, alias="open"),
):
    # Tauri file association: open a project before rendering the coding page
    if open_path:
        from ace.db.connection import open_project
        from ace.models.project import list_coders

        try:
            conn = open_project(open_path)
        except (ValueError, FileNotFoundError, sqlite3.DatabaseError):
            raise HtmxRedirect("/")
        try:
            coders = list_coders(conn)
        finally:
            conn.close()
        request.app.state.project_path = str(open_path)
        if coders:
            request.app.state.coder_id = coders[0]["id"]
        request.app.state.active_projects.add(str(open_path))

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

        context = _coding_context(conn, coder_id, index, project_path=project_path)
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "coding.html", context)


@router.get("/code/{code_id}/view", response_class=HTMLResponse)
async def code_view_page(request: Request, code_id: str):
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    coder_id: str | None = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        data = get_code_view_data(conn, code_id, coder_id)
        if data is None:
            raise HtmxRedirect("/code")
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "code_view.html",
        {"code_view_data": data},
    )
