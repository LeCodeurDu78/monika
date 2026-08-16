"""
tools/utils/reminder_tools.py
------------------------------
Gestion des rappels/tâches avec échéance pour Monika, stockés en SQLite.

Trois usages :
1. Le modèle peut créer, lister ou supprimer des rappels via function calling
   (actions 'add', 'list', 'delete').
2. Le modèle peut aussi vérifier explicitement s'il y a des rappels en
   attente (action 'due'), par exemple si l'utilisateur demande
   "j'ai des rappels ?".
3. agent.py utilise la même action 'due' en tâche de fond (voir
   `_start_reminder_watcher`) pour annoncer proactivement un rappel dès son
   échéance, sans que l'utilisateur ait à demander quoi que ce soit.

Un rappel n'est annoncé (via 'due') qu'une seule fois : dès qu'il est
renvoyé par 'due', il est marqué 'notified' pour ne pas être répété en boucle.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.expanduser("~/.config/monika/reminders.db")


def _init_db() -> None:
    """Initialise la table des rappels si elle n'existe pas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message TEXT NOT NULL,
                due_at TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def _parse_due_at(due_at: str) -> datetime:
    """Parse une date/heure ISO (ex: '2026-08-20T09:00:00'). Lève ValueError si invalide."""
    return datetime.fromisoformat(due_at.strip())


def reminder_control(
    action: str,
    message: str = "",
    due_at: str = "",
    reminder_id: int = 0,
    limit: int = 10,
) -> str:
    """Gère les rappels avec échéance de Monika.

    Actions disponibles :
    - 'add'    : Crée un rappel (requiert 'message' et 'due_at' au format ISO,
                 ex: '2026-08-20T09:00:00').
    - 'list'   : Liste les prochains rappels à venir (non expirés).
    - 'delete' : Supprime un rappel par son identifiant (requiert 'reminder_id',
                 visible via 'list').
    - 'due'    : Renvoie les rappels arrivés à échéance et pas encore annoncés,
                 puis les marque comme annoncés. Utilisé aussi en tâche de fond.
    """
    _init_db()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "add":
                if not message.strip() or not due_at.strip():
                    return "Erreur : 'message' et 'due_at' (format ISO, ex: '2026-08-20T09:00:00') sont requis."
                try:
                    parsed = _parse_due_at(due_at)
                except ValueError:
                    return f"Erreur : '{due_at}' n'est pas une date/heure ISO valide (ex: '2026-08-20T09:00:00')."

                cursor.execute(
                    "INSERT INTO reminders (message, due_at) VALUES (?, ?)",
                    (message.strip(), parsed.isoformat()),
                )
                conn.commit()
                return f"⏰ Rappel créé : « {message.strip()} » pour le {parsed.strftime('%d/%m/%Y à %H:%M')}."

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
                return f"🗑️ Rappel #{reminder_id} supprimé."

            elif action == "due":
                cursor.execute(
                    "SELECT id, message FROM reminders WHERE due_at <= ? AND notified = 0 ORDER BY due_at",
                    (datetime.now().isoformat(),),
                )
                rows = cursor.fetchall()
                if not rows:
                    return ""  # chaîne vide = rien à annoncer, utilisé tel quel par le watcher en tâche de fond

                ids = [row_id for row_id, _ in rows]
                placeholders = ",".join("?" * len(ids))
                cursor.execute(f"UPDATE reminders SET notified = 1 WHERE id IN ({placeholders})", ids)
                conn.commit()

                return "\n".join(f"⏰ Rappel : {msg}" for _, msg in rows)

            return "Action non reconnue pour l'outil reminder_control."

    except Exception as e:
        return f"Erreur lors de la gestion des rappels : {str(e)}"
