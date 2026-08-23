"""Analyse visuelle passive de Monika : capture périodique de l'écran, filtrage par diff perceptif
pour ne pas payer un appel au modèle vision à chaque tick, et journalisation en SQLite.

Ce log (screen_log.db) sert de base à l'analyse contextuelle prévue en v3.
"""

import io
import platform
import sqlite3
import subprocess
import threading
from typing import Callable, Optional

from PIL import Image

from config import (
    APP_DIR,
    SCREEN_WATCH_ENABLED,
    SCREEN_WATCH_HASH_THRESHOLD,
    SCREEN_WATCH_INTERVAL_SECONDS,
)
from tools.system.vision_tools import analyze_image

DB_PATH = str(APP_DIR / "screen_log.db")

DEFAULT_PROMPT = (
    "Décris en 2-3 phrases maximum ce qui est visible à l'écran : application active, "
    "contenu principal, activité probable de l'utilisateur."
)


def _init_db() -> None:
    """Crée la table screen_log si nécessaire (même pattern que reminder_tools._init_db)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS screen_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                image_hash TEXT NOT NULL,
                analysis TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _capture_screen_bytes() -> Optional[bytes]:
    """Capture l'écran courant et renvoie des bytes PNG en mémoire (rien n'est écrit sur disque).
    Windows : PIL ImageGrab. Linux (Wayland) : grim, écrit sur stdout via '-' (même outil que
    system_control('screenshot'))."""
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
    """Hash perceptif simple (average hash) : sous-échantillonne l'image en niveaux de gris
    hash_size x hash_size, puis code 1 bit par pixel selon sa position par rapport à la moyenne."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        small = img.convert("L").resize((hash_size, hash_size), Image.LANCZOS)
        pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):0{hash_size * hash_size // 4}x}"


def _hamming_distance(hash_a: str, hash_b: str) -> int:
    """Nombre de bits différents entre deux hashs perceptifs (0 = images quasi identiques)."""
    return bin(int(hash_a, 16) ^ int(hash_b, 16)).count("1")


def _log_analysis(image_hash: str, analysis: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO screen_log (image_hash, analysis) VALUES (?, ?)",
            (image_hash, analysis),
        )
        conn.commit()


def _start_screen_watcher(
    on_analysis: Callable[[str], None] = lambda text: None,
    prompt: str = DEFAULT_PROMPT,
) -> threading.Event:
    """Démarre un thread démon (même pattern que _start_reminder_watcher) qui, toutes les
    SCREEN_WATCH_INTERVAL_SECONDS, capture l'écran et n'appelle le modèle vision que si l'écran a
    significativement changé depuis la dernière capture retenue (distance de Hamming entre hashs
    perceptifs >= SCREEN_WATCH_HASH_THRESHOLD), afin de maîtriser le coût API. Chaque analyse est
    journalisée dans APP_DIR / 'screen_log.db'.

    Si SCREEN_WATCH_ENABLED est désactivé, renvoie un Event déjà inoffensif sans démarrer de thread.
    """
    stop_event = threading.Event()

    if not SCREEN_WATCH_ENABLED:
        return stop_event

    _init_db()
    last_hash: Optional[str] = None

    def _loop() -> None:
        nonlocal last_hash
        while not stop_event.wait(SCREEN_WATCH_INTERVAL_SECONDS):
            image_bytes = _capture_screen_bytes()
            if not image_bytes:
                continue

            try:
                current_hash = _perceptual_hash(image_bytes)
            except Exception as e:
                print(f"⚠️ [screen_watcher] Échec du hash perceptif : {e}")
                continue

            if last_hash is not None and _hamming_distance(last_hash, current_hash) < SCREEN_WATCH_HASH_THRESHOLD:
                continue  # écran quasi inchangé : on évite un appel API vision inutile

            last_hash = current_hash

            try:
                analysis = analyze_image(image_bytes, prompt=prompt, mime_type="image/png")
            except Exception as e:
                analysis = f"Erreur lors de l'analyse d'écran : {e}"

            _log_analysis(current_hash, analysis)
            on_analysis(analysis)

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event
