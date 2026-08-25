"""Apprentissage comportemental"""

import queue
import threading
from datetime import datetime

from config import BEHAVIOR_LOG_ENABLED
from core.db import db_path, get_connection, init_table

DB_PATH = db_path("behavior.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS behavior_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        tool_name TEXT,
        detail TEXT,
        hour_of_day INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""

CORRECTION_MARKERS = (
    "non,", "non je", "non c'est", "je voulais dire", "en fait", "pas ça",
    "trop formel", "trop familier", "c'est pas ce que", "je n'ai pas dit",
    "corrige", "erreur", "c'est faux", "pas correct",
)

_write_queue: "queue.Queue[tuple]" = queue.Queue()
_writer_started = False
_writer_lock = threading.Lock()


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _writer_loop() -> None:
    """Thread de fond : dépile et écrit les événements sans bloquer l'appelant."""
    _init_db()
    while True:
        event_type, tool_name, detail = _write_queue.get()
        try:
            with get_connection(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO behavior_log (event_type, tool_name, detail, hour_of_day) "
                    "VALUES (?, ?, ?, ?)",
                    (event_type, tool_name, detail, datetime.now().hour),
                )
                conn.commit()
        except Exception as e:
            print(f"⚠️ [behavior_log] Échec d'écriture d'un événement : {e}")
        finally:
            _write_queue.task_done()


def _ensure_writer_started() -> None:
    global _writer_started
    if _writer_started:
        return
    with _writer_lock:
        if _writer_started:
            return
        threading.Thread(target=_writer_loop, daemon=True).start()
        _writer_started = True


def log_behavior_event(event_type: str, tool_name: str = "", detail: str = "") -> None:
    """Journalise un événement comportemental de façon asynchrone."""
    if not BEHAVIOR_LOG_ENABLED:
        return
    _ensure_writer_started()
    _write_queue.put((event_type, tool_name.strip(), detail.strip()[:500]))


def looks_like_correction(user_text: str) -> bool:
    """Heuristique légère : le message ressemble-t-il à une correction de la réponse précédente ?"""
    lowered = user_text.strip().lower()
    return any(marker in lowered for marker in CORRECTION_MARKERS)


def get_behavior_summary(days: int = 14) -> str:
    """Résume les patterns récents d'usage."""
    _init_db()
    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT tool_name, COUNT(*) c FROM behavior_log "
                "WHERE event_type = 'tool_call' AND tool_name IS NOT NULL AND tool_name != '' "
                "AND created_at >= datetime('now', ?) "
                "GROUP BY tool_name ORDER BY c DESC LIMIT 5",
                (f"-{int(days)} days",),
            )
            top_tools = cursor.fetchall()

            cursor.execute(
                "SELECT hour_of_day, COUNT(*) c FROM behavior_log "
                "WHERE created_at >= datetime('now', ?) "
                "GROUP BY hour_of_day ORDER BY c DESC LIMIT 3",
                (f"-{int(days)} days",),
            )
            top_hours = cursor.fetchall()

            cursor.execute(
                "SELECT COUNT(*) FROM behavior_log "
                "WHERE event_type = 'correction' AND created_at >= datetime('now', ?)",
                (f"-{int(days)} days",),
            )
            correction_count = cursor.fetchone()[0]

            cursor.execute(
                "SELECT detail FROM behavior_log "
                "WHERE event_type = 'correction' AND detail IS NOT NULL AND detail != '' "
                "ORDER BY created_at DESC LIMIT 5"
            )
            recent_corrections = [row[0] for row in cursor.fetchall()]

    except Exception as e:
        return f"Erreur lors de la lecture du journal comportemental : {str(e)}"

    if not top_tools and not top_hours and correction_count == 0:
        return "Pas encore assez de données comportementales pour dégager un pattern."

    lines = []
    if top_tools:
        tools_str = ", ".join(f"{name} ({count}x)" for name, count in top_tools)
        lines.append(f"Outils les plus utilisés récemment : {tools_str}.")
    if top_hours:
        hours_str = ", ".join(f"{h}h" for h, _ in top_hours)
        lines.append(f"Heures d'usage les plus fréquentes : {hours_str}.")
    if correction_count:
        lines.append(
            f"L'utilisateur a corrigé Monika {correction_count} fois sur les {days} derniers jours."
        )
        if recent_corrections:
            joined = " / ".join(c[:80] for c in recent_corrections)
            lines.append(f"Corrections récentes (extraits) : {joined}")

    return " ".join(lines)


def behavior_control(action: str) -> str:
    """Consulte ou vide le journal comportemental de Monika."""
    _init_db()

    if action == "show":
        return get_behavior_summary()

    if action == "reset":
        try:
            with get_connection(DB_PATH) as conn:
                conn.execute("DELETE FROM behavior_log")
                conn.commit()
            return "🧹 Journal comportemental vidé."
        except Exception as e:
            return f"Erreur lors de la suppression du journal comportemental : {str(e)}"

    return "Action non reconnue pour l'outil behavior_control (utilise 'show' ou 'reset')."
