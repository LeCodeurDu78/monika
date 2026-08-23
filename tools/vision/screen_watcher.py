"""Analyse visuelle passive de Monika."""

import io
import platform
import subprocess
import threading
from typing import Callable, Optional

from PIL import Image

from config import (
    SCREEN_WATCH_ENABLED,
    SCREEN_WATCH_HASH_THRESHOLD,
    SCREEN_WATCH_INTERVAL_SECONDS,
)
from core.db import db_path, get_connection, init_table
from core.watcher import start_watcher
from tools.vision.vision_tools import analyze_image

DB_PATH = db_path("screen_log.db")

DEFAULT_PROMPT = (
    "Décris en 2-3 phrases maximum ce qui est visible à l'écran : application active, "
    "contenu principal, activité probable de l'utilisateur."
)


_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS screen_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        image_hash TEXT NOT NULL,
        analysis TEXT NOT NULL
    )
"""


def _init_db() -> None:
    """Crée la table screen_log si nécessaire."""
    init_table(DB_PATH, _CREATE_SQL)


def _capture_screen_bytes() -> Optional[bytes]:
    """Capture l'écran courant et renvoie des bytes PNG en mémoire."""
    try:
        if platform.system() == "Windows":
            from PIL import ImageGrab

            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        else:
            result = subprocess.run(["grim", "-"], capture_output=True, check=True)
            return result.stdout
    except Exception as e:
        print(f"⚠️ [screen_watcher] Échec de la capture d'écran : {e}")
        return None


def _perceptual_hash(image_bytes: bytes, hash_size: int = 8) -> str:
    """Hash perceptif simple (average hash)."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        small = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def _hamming_distance(hash_a: str, hash_b: str) -> int:
    """Nombre de bits différents entre deux hashs perceptifs."""
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def _log_analysis(image_hash: str, analysis: str) -> None:
    with get_connection(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO screen_log (image_hash, analysis) VALUES (?, ?)",
            (image_hash, analysis),
        )
        conn.commit()


def _start_screen_watcher(
    on_analysis: Callable[[str], None] = lambda text: None,
    prompt: str = DEFAULT_PROMPT,
) -> threading.Event:
    """Démarre un watcher."""
    if not SCREEN_WATCH_ENABLED:
        return threading.Event()

    _init_db()
    last_hash: Optional[str] = None

    def _tick() -> None:
        nonlocal last_hash
        image_bytes = _capture_screen_bytes()
        if not image_bytes:
            return

        try:
            current_hash = _perceptual_hash(image_bytes)
        except Exception as e:
            print(f"⚠️ [screen_watcher] Échec du hash perceptif : {e}")
            return

        if last_hash is not None and _hamming_distance(last_hash, current_hash) < SCREEN_WATCH_HASH_THRESHOLD:
            return

        last_hash = current_hash

        try:
            analysis = analyze_image(image_bytes, prompt=prompt, mime_type="image/png")
        except Exception as e:
            analysis = f"Erreur lors de l'analyse d'écran : {e}"

        _log_analysis(current_hash, analysis)
        on_analysis(analysis)

    return start_watcher(SCREEN_WATCH_INTERVAL_SECONDS, _tick)
