from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

UI_DIR = Path(__file__).resolve().parent.parent / "ui"

# The page loads only its own script and stylesheet and talks only to this server.
PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

router = APIRouter()


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(UI_DIR / "index.html", headers=PAGE_HEADERS)
