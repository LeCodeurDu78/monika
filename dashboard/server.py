"""Dashboard web de Monika."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from core.settings import settings
from core.wake.wake_store import main_process_is_alive
from tools.registry import TOOL_DEFS

_STATIC_DIR = Path(__file__).parent / "static"
_AVATAR_DIR = _STATIC_DIR / "avatar"
_AVATAR_MODEL_FILENAMES = ("monika.glb", "monika.gltf")

_start_time = time.monotonic()

app = FastAPI(title="Monika Dashboard")


def _find_avatar_model() -> str | None:
    """Renvoie le nom du fichier de modèle 3D si un a été déposé dans static/avatar/."""
    for name in _AVATAR_MODEL_FILENAMES:
        if (_AVATAR_DIR / name).exists():
            return name
    return None


@app.get("/api/status")
def get_status() -> dict:
    """Statut courant de Monika, consommé par le frontend en polling."""
    uptime_seconds = int(time.monotonic() - _start_time)
    avatar_model = _find_avatar_model()
    return {
        "name": "Monika",
        "online": main_process_is_alive(),
        "dashboard_uptime_seconds": uptime_seconds,
        "tool_count": len(TOOL_DEFS),
        "features": {
            "proactive": settings.PROACTIVE_ENABLED,
            "morning_briefing": settings.MORNING_BRIEFING_ENABLED,
            "screen_watch": settings.SCREEN_WATCH_ENABLED,
            "curator": settings.CURATOR_ENABLED,
        },
        "avatar": {
            "model_available": avatar_model is not None,
            "model_file": avatar_model,
        },
    }


@app.get("/")
def get_index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


# Fichiers statiques (css/js) + emplacement dédié au futur modèle 3D animé.
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")


def _run_server() -> None:
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    uvicorn.run(app, host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT, log_level="warning")


def start_dashboard() -> threading.Event:
    """Démarre le dashboard dans un thread démon. Renvoie un Event (non utilisé pour l'arrêt :
    uvicorn.run bloque le thread ; l'Event est fourni uniquement pour rester compatible avec la
    liste de stop_events de _start_background_watchers)."""
    stop_event = threading.Event()
    threading.Thread(target=_run_server, daemon=True).start()
    return stop_event
