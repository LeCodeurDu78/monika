"""Serveur web du compagnon 3D de Monika.

Sert la page Three.js (avatar/static/index.html + avatar/static/model.glb) et
une petite API JSON que la page interroge par polling pour savoir dans quel
état se trouve Monika (idle / listening / thinking / speaking) et à quelle
amplitude animer la mâchoire.

Tourne dans un thread daemon à part, via uvicorn, pour ne jamais bloquer la
boucle de conversation existante (qui reste 100% synchrone).
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from avatar import state as avatar_state
from core.settings import settings

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Monika Avatar")


@app.get("/api/state")
def get_state() -> dict:
    return avatar_state.snapshot()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Le modèle 3D (monika.glb, renommé model.glb) et tout autre asset statique.
app.mount("/", StaticFiles(directory=str(STATIC_DIR)), name="static")

_server_thread: threading.Thread | None = None


def _run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="warning")


def start_avatar_server() -> None:
    """Démarre le serveur (une seule fois) et ouvre le navigateur si configuré."""
    global _server_thread

    if not settings.AVATAR_ENABLED:
        return

    if not (STATIC_DIR / "model.glb").exists():
        print(
            f"⚠️ Avatar 3D désactivé : fichier introuvable ({STATIC_DIR / 'model.glb'}). "
            "Placez-y votre .glb (voir avatar/static/model.glb)."
        )
        return

    if _server_thread is not None and _server_thread.is_alive():
        return  # déjà démarré

    host, port = settings.AVATAR_HOST, settings.AVATAR_PORT
    _server_thread = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    _server_thread.start()

    print(f"🧑‍🎨 Avatar 3D disponible sur http://{host}:{port}")

    if settings.AVATAR_OPEN_BROWSER:
        webbrowser.open(f"http://{host}:{port}")
