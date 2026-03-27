"""Page routes — HTML responses rendered via Jinja2."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ace.app import HtmxRedirect, get_db
from ace.models.project import get_project
from ace.models.source import list_sources

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
