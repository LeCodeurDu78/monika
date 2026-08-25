"""Analyse visuelle passive de Monika."""

import io
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
from tools.system.screen_context import capture_screen_bytes, get_screen_context
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
        analysis TEXT NOT NULL,
        app TEXT,
        window_title TEXT,
        activity_guess TEXT,
        raw_text TEXT
    )
"""

_COLUMNS = ("app", "window_title", "activity_guess", "raw_text")


def _init_db() -> None:
    """Crée la table screen_log si nécessaire, et migre le schéma si une v6 sans colonnes v4 existe déjà."""
    init_table(DB_PATH, _CREATE_SQL)
    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(screen_log)")}
        for column in _COLUMNS:
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE screen_log ADD COLUMN {column} TEXT")
        conn.commit()


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


def _log_context(image_hash: str, context: dict) -> None:
    with get_connection(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO screen_log (image_hash, analysis, app, window_title, activity_guess, raw_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                image_hash,
                context.get("activity_guess", ""),
                context.get("app", ""),
                context.get("window_title", ""),
                context.get("activity_guess", ""),
                context.get("raw_text", ""),
            ),
        )
        conn.commit()


def get_latest_screen_context() -> Optional[dict]:
    """Renvoie le dernier résumé structuré loggé."""
    _init_db()
    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT app, window_title, activity_guess, raw_text, timestamp FROM screen_log "
            "ORDER BY id DESC LIMIT 1"
        )
        row = cursor.fetchone()
    if not row:
        return None
    app, window_title, activity_guess, raw_text, timestamp = row
    return {
        "app": app or "",
        "window_title": window_title or "",
        "activity_guess": activity_guess or "",
        "raw_text": raw_text or "",
        "timestamp": timestamp,
    }


def _start_screen_watcher(
    on_analysis: Callable[[str], None] = lambda text: None,
    on_context: Callable[[dict], None] = lambda context: None,
    prompt: str = DEFAULT_PROMPT,
) -> threading.Event:
    """Démarre un watcher."""
    if not SCREEN_WATCH_ENABLED:
        return threading.Event()

    _init_db()
    last_hash: Optional[str] = None

    def _tick() -> None:
        nonlocal last_hash
        image_bytes = capture_screen_bytes()
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

        try:
            context = get_screen_context(image_bytes=image_bytes, vision_description=analysis)
        except Exception as e:
            context = {"app": "", "window_title": "", "activity_guess": analysis, "raw_text": ""}
            print(f"⚠️ [screen_watcher] Échec de l'analyse contextuelle structurée : {e}")

        _log_context(current_hash, context)
        on_analysis(context.get("activity_guess", analysis))
        on_context(context)

    return start_watcher(SCREEN_WATCH_INTERVAL_SECONDS, _tick)
