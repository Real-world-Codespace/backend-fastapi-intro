from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

router = APIRouter(tags=["system"])
STATIC_DIR = Path(__file__).resolve().parents[1] / "static"


@router.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/api/health")
def health(request: Request):
    return {"status": "ok", "ai_mode": request.app.state.settings.ai_mode}
