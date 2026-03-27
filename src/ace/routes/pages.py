"""Page routes — HTML responses rendered via Jinja2."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ace.app import HtmxRedirect

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "landing.html")


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    if getattr(request.app.state, "db", None) is None:
        raise HtmxRedirect("/")
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "import.html")
