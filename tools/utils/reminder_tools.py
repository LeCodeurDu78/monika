"""Rappels avec échéance pour Monika, stockés en SQLite."""

from datetime import datetime

from core.db import db_path, get_connection, init_table
from core.native_scheduler import register_once, unregister
from core.settings import settings

DB_PATH = db_path("reminders.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT NOT NULL,
        due_at TEXT NOT NULL,
        notified INTEGER NOT NULL DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _parse_due_at(due_at: str) -> datetime:
    """Parse une date/heure ISO (ex: '2026-08-20T09:00:00')."""
    return datetime.fromisoformat(due_at.strip())


def reminder_control(
    action: str,
    message: str = "",
    due_at: str = "",
    reminder_id: int = 0,
    limit: int = 10,
) -> str:
    """Gère les rappels avec échéance de Monika."""
    _init_db()

    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "add":
                if not message.strip() or not due_at.strip():
                    return (
                        "Erreur : 'message' et 'due_at' (format ISO, ex: '2026-08-20T09:00:00') sont requis."
                    )
                try:
                    parsed = _parse_due_at(due_at)
                except ValueError:
                    return f"Erreur : '{due_at}' n'est pas une date/heure ISO valide (ex: '2026-08-20T09:00:00')."

                cursor.execute(
                    "INSERT INTO reminders (message, due_at) VALUES (?, ?)",
                    (message.strip(), parsed.isoformat()),
                )
                conn.commit()
                new_id = cursor.lastrowid

                if settings.NATIVE_SCHEDULING_ENABLED:
                    # Filet de sécurité : réveille Monika via le planificateur natif de l'OS à
                    # l'échéance, même si le process principal n'est pas actif (voir wake_runner.py).
                    register_once(f"reminder_{new_id}", parsed, kind="reminder", ref_id=new_id)

                return (
                    f"⏰ Rappel créé : « {message.strip()} » pour le {parsed.strftime('%d/%m/%Y à %H:%M')}."
                )

            elif action == "list":
                cursor.execute(
                    "SELECT id, message, due_at FROM reminders WHERE due_at >= ? ORDER BY due_at LIMIT ?",
                    (datetime.now().isoformat(), limit),
                )
                rows = cursor.fetchall()
                if not rows:
                    return "Aucun rappel à venir."

                lines = [
                    f"• [#{rid}] {datetime.fromisoformat(due).strftime('%d/%m/%Y %H:%M')} : {msg}"
                    for rid, msg, due in rows
                ]
                return "Prochains rappels :\n" + "\n".join(lines)

            elif action == "delete":
                if not reminder_id:
                    return "Erreur : 'reminder_id' est requis pour supprimer un rappel (voir action='list')."
                cursor.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                conn.commit()
                if cursor.rowcount == 0:
                    return f"Aucun rappel trouvé avec l'identifiant #{reminder_id}."

                if settings.NATIVE_SCHEDULING_ENABLED:
                    unregister(f"reminder_{reminder_id}")

                return f"🗑️ Rappel #{reminder_id} supprimé."

            elif action == "due":
                cursor.execute(
                    "SELECT id, message FROM reminders WHERE due_at <= ? AND notified = 0 ORDER BY due_at",
                    (datetime.now().isoformat(),),
                )
                rows = cursor.fetchall()
                if not rows:
                    return ""

                ids = [row_id for row_id, _ in rows]
                placeholders = ",".join("?" * len(ids))
                cursor.execute(f"UPDATE reminders SET notified = 1 WHERE id IN ({placeholders})", ids)
                conn.commit()

                if settings.NATIVE_SCHEDULING_ENABLED:
                    # Rappels consommés : on retire les déclenchements natifs ponctuels associés.
                    for row_id in ids:
                        unregister(f"reminder_{row_id}")

                return "\n".join(f"⏰ Rappel : {msg}" for _, msg in rows)

            return "Action non reconnue pour l'outil reminder_control."

    except Exception as e:
        return f"Erreur lors de la gestion des rappels : {str(e)}"
