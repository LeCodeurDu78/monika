"""État et coordination partagés du sous-système de réveil natif."""

import os
from datetime import date

import psutil

from core.db import db_path, get_connection, init_table

# --- Verrou de process ---------------------------------------------------------------------

LOCK_PATH = db_path("agent.lock")


def acquire() -> None:
    """Écrit le PID courant dans le fichier de verrou. À appeler au démarrage de la boucle principale."""
    with open(LOCK_PATH, "w") as f:
        f.write(str(os.getpid()))


def release() -> None:
    """Supprime le verrou. À appeler à l'arrêt propre de la boucle principale."""
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass


def main_process_is_alive() -> bool:
    """Indique si le PID enregistré dans le verrou correspond encore à un process actif."""
    try:
        with open(LOCK_PATH) as f:
            pid = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return False

    return psutil.pid_exists(pid)


# --- État quotidien (dédup briefing / tâches journalières) ---------------------------------

_STATE_DB_PATH = db_path("wake_state.db")

_STATE_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS daily_task_state (
        task_key TEXT PRIMARY KEY,
        last_run_date TEXT
    )
"""


def _init_state_db() -> None:
    init_table(_STATE_DB_PATH, _STATE_CREATE_SQL)


def should_run_today(task_key: str) -> bool:
    """True si `task_key` n'a pas encore été exécutée aujourd'hui."""
    _init_state_db()
    today = date.today().isoformat()
    with get_connection(_STATE_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_run_date FROM daily_task_state WHERE task_key = ?", (task_key,))
        row = cursor.fetchone()
    return row is None or row[0] != today


def mark_ran_today(task_key: str) -> None:
    """Marque `task_key` comme exécutée aujourd'hui."""
    _init_state_db()
    today = date.today().isoformat()
    with get_connection(_STATE_DB_PATH) as conn:
        conn.execute(
            """INSERT INTO daily_task_state (task_key, last_run_date) VALUES (?, ?)
               ON CONFLICT(task_key) DO UPDATE SET last_run_date = excluded.last_run_date""",
            (task_key, today),
        )
        conn.commit()


# --- Boîte de réveil (résultats à annoncer au prochain démarrage) --------------------------

_OUTBOX_DB_PATH = db_path("wake_outbox.db")

_OUTBOX_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS wake_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""


def _init_outbox_db() -> None:
    init_table(_OUTBOX_DB_PATH, _OUTBOX_CREATE_SQL)


def push_wake_result(kind: str, message: str) -> None:
    """Empile un résultat produit hors session interactive (réveil natif, process principal absent)."""
    _init_outbox_db()
    with get_connection(_OUTBOX_DB_PATH) as conn:
        conn.execute("INSERT INTO wake_outbox (kind, message) VALUES (?, ?)", (kind, message))
        conn.commit()


def drain_wake_results() -> list[tuple[str, str]]:
    """Récupère puis vide tous les messages en attente. À appeler au démarrage de la session interactive."""
    _init_outbox_db()
    with get_connection(_OUTBOX_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT kind, message FROM wake_outbox ORDER BY id")
        rows = cursor.fetchall()
        cursor.execute("DELETE FROM wake_outbox")
        conn.commit()
    return rows
