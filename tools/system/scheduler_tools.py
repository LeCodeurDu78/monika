"""
tools/system/scheduler_tools.py
--------------------------------
Planification de tâches en arrière-plan pour Monika — l'équivalent d'un cron
personnel.

Différence avec reminder_tools.py : un rappel se contente d'ANNONCER un
message, tandis qu'une tâche planifiée ici déclenche une EXÉCUTION AUTONOME
par l'agent (l'instruction est envoyée au modèle, qui peut appeler n'importe
quel outil pour l'accomplir).

Trois types de récurrence : 'once' (date/heure précise via 'run_at'), 'daily'
('time_of_day', format 'HH:MM'), 'interval' (boucle toutes les N secondes).

Ce module ne gère que le stockage (CRUD) des tâches. L'exécution réelle est
déclenchée par le thread de fond de agent.py (`_start_scheduler_watcher`),
seul à connaître `process_user_message` — ça évite un import circulaire.
"""

import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.expanduser("~/.config/monika/scheduler.db")

VALID_SCHEDULE_TYPES = ("once", "daily", "interval")
SCHEDULE_LABELS = {"once": "une fois", "daily": "tous les jours", "interval": "en boucle"}


def _init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instruction TEXT NOT NULL,
                schedule_type TEXT NOT NULL,
                run_at TEXT,
                time_of_day TEXT,
                interval_seconds INTEGER,
                next_run TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def _parse_time_of_day(value: str) -> tuple[int, int]:
    """Parse une heure 'HH:MM'. Lève ValueError si invalide."""
    hour_str, minute_str = value.strip().split(":")
    hour, minute = int(hour_str), int(minute_str)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"heure hors limites : {value}")
    return hour, minute


def _next_daily_run(time_of_day: str, after: datetime | None = None) -> datetime:
    """Calcule la prochaine occurrence de `time_of_day` strictement après `after`."""
    after = after or datetime.now()
    hour, minute = _parse_time_of_day(time_of_day)
    candidate = after.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= after:
        candidate += timedelta(days=1)
    return candidate


def scheduler_control(
    action: str,
    instruction: str = "",
    schedule_type: str = "",
    run_at: str = "",
    time_of_day: str = "",
    interval_seconds: int = 0,
    task_id: int = 0,
) -> str:
    """Planifie, liste ou annule des tâches exécutées de façon autonome par Monika.

    Actions disponibles :
    - 'add'    : Planifie une tâche (requiert 'instruction' et 'schedule_type',
                 plus 'run_at'/'time_of_day'/'interval_seconds' selon le type).
    - 'list'   : Liste les tâches planifiées actives et leur prochain déclenchement.
    - 'cancel' : Annule une tâche planifiée (requiert 'task_id', voir action='list').
    """
    _init_db()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "add":
                if not instruction.strip():
                    return "Erreur : 'instruction' est requis (ce que Monika doit faire, ex: 'donne la météo de Paris')."
                if schedule_type not in VALID_SCHEDULE_TYPES:
                    return f"Erreur : 'schedule_type' doit être l'un de {VALID_SCHEDULE_TYPES}."

                if schedule_type == "once":
                    if not run_at.strip():
                        return "Erreur : 'run_at' (date/heure ISO, ex: '2026-08-20T09:00:00') est requis pour schedule_type='once'."
                    try:
                        next_run = datetime.fromisoformat(run_at.strip())
                    except ValueError:
                        return f"Erreur : '{run_at}' n'est pas une date/heure ISO valide."
                elif schedule_type == "daily":
                    if not time_of_day.strip():
                        return "Erreur : 'time_of_day' (format 'HH:MM', ex: '08:00') est requis pour schedule_type='daily'."
                    try:
                        next_run = _next_daily_run(time_of_day.strip())
                    except ValueError:
                        return f"Erreur : '{time_of_day}' n'est pas une heure valide (format attendu : 'HH:MM')."
                else:  # interval
                    if interval_seconds <= 0:
                        return "Erreur : 'interval_seconds' doit être un entier positif pour schedule_type='interval'."
                    next_run = datetime.now() + timedelta(seconds=interval_seconds)

                cursor.execute(
                    """INSERT INTO scheduled_tasks
                       (instruction, schedule_type, run_at, time_of_day, interval_seconds, next_run)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        instruction.strip(),
                        schedule_type,
                        run_at.strip() or None,
                        time_of_day.strip() or None,
                        interval_seconds or None,
                        next_run.isoformat(),
                    ),
                )
                conn.commit()
                return (
                    f"🗓️ Tâche planifiée (#{cursor.lastrowid}, {SCHEDULE_LABELS[schedule_type]}) : "
                    f"« {instruction.strip()} » — prochain déclenchement le {next_run.strftime('%d/%m/%Y à %H:%M')}."
                )

            elif action == "list":
                cursor.execute(
                    "SELECT id, instruction, schedule_type, next_run FROM scheduled_tasks WHERE active = 1 ORDER BY next_run"
                )
                rows = cursor.fetchall()
                if not rows:
                    return "Aucune tâche planifiée active."

                lines = [
                    f"• [#{tid}] ({SCHEDULE_LABELS[stype]}) {instr} — prochain : {datetime.fromisoformat(nr).strftime('%d/%m/%Y %H:%M')}"
                    for tid, instr, stype, nr in rows
                ]
                return "Tâches planifiées :\n" + "\n".join(lines)

            elif action == "cancel":
                if not task_id:
                    return "Erreur : 'task_id' est requis pour annuler une tâche (voir action='list')."
                cursor.execute("UPDATE scheduled_tasks SET active = 0 WHERE id = ?", (task_id,))
                conn.commit()
                if cursor.rowcount == 0:
                    return f"Aucune tâche planifiée trouvée avec l'identifiant #{task_id}."
                return f"🛑 Tâche planifiée #{task_id} annulée."

            return "Action non reconnue pour l'outil scheduler_control."

    except Exception as e:
        return f"Erreur lors de la gestion des tâches planifiées : {str(e)}"


def pop_due_tasks() -> list[tuple[int, str]]:
    """Récupère les tâches actives arrivées à échéance et avance leur
    prochaine exécution ('daily'/'interval') ou les désactive ('once').

    Usage interne : appelé par le thread de fond de agent.py, jamais exposé
    au modèle via function calling.
    """
    _init_db()
    due: list[tuple[int, str]] = []

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, instruction, schedule_type, time_of_day, interval_seconds, next_run "
            "FROM scheduled_tasks WHERE active = 1 AND next_run <= ?",
            (datetime.now().isoformat(),),
        )
        rows = cursor.fetchall()

        for task_id, instruction, schedule_type, time_of_day, interval_seconds, next_run in rows:
            due.append((task_id, instruction))

            if schedule_type == "once":
                cursor.execute("UPDATE scheduled_tasks SET active = 0 WHERE id = ?", (task_id,))
            elif schedule_type == "daily":
                new_next = _next_daily_run(time_of_day, after=datetime.fromisoformat(next_run))
                cursor.execute("UPDATE scheduled_tasks SET next_run = ? WHERE id = ?", (new_next.isoformat(), task_id))
            elif schedule_type == "interval":
                # Repart de "maintenant" plutôt que d'accumuler du retard si Monika était éteinte.
                new_next = datetime.now() + timedelta(seconds=interval_seconds)
                cursor.execute("UPDATE scheduled_tasks SET next_run = ? WHERE id = ?", (new_next.isoformat(), task_id))

        conn.commit()

    return due