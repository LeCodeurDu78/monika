"""Curator nocturne."""

import sqlite3
from datetime import datetime

from core.db import db_path, get_connection, init_table
from core.settings import settings

DB_PATH = db_path("curator.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS curator_reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_date TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""

_CURATOR_INSTRUCTION = (
    "Exécute la curation nocturne de Monika en appelant l'outil run_nightly_curator, "
    "puis confirme brièvement que le rapport a été généré."
)


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _store_report(content: str) -> None:
    _init_db()
    with get_connection(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO curator_reports (report_date, content) VALUES (?, ?)",
            (datetime.now().date().isoformat(), content),
        )
        conn.commit()


def run_nightly_curator() -> str:
    """Génère et stocke le rapport de curation nocturne."""
    from agents.proactive import list_initiatives
    from tools.knowledge.memory_tools import export_memory_markdown, facts_needing_review
    from tools.system.behavior_tools import get_behavior_summary

    behavior = get_behavior_summary(days=1)
    initiatives = list_initiatives(days=1)
    facts_review = facts_needing_review()

    try:
        export_note = export_memory_markdown()
    except Exception as e:
        export_note = f"⚠️ Échec de l'export mémoire : {e}"

    report = (
        f"🌙 Curation nocturne du {datetime.now().strftime('%d/%m/%Y')}\n\n"
        f"Comportement (24h) :\n{behavior}\n\n"
        f"Initiatives du jour :\n{initiatives}\n\n"
        f"Faits à vérifier :\n{facts_review or 'Aucun.'}\n\n"
        f"Export mémoire : {export_note}"
    )

    _store_report(report)
    return report


def _curator_already_scheduled() -> bool:
    """Évite de réinsérer une tâche planifiée en double à chaque démarrage de Monika."""
    from tools.utils.scheduler_tools import DB_PATH as SCHEDULER_DB_PATH

    try:
        with get_connection(SCHEDULER_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM scheduled_tasks WHERE instruction = ? AND schedule_type = 'daily' AND active = 1",
                (_CURATOR_INSTRUCTION,),
            )
            return cursor.fetchone() is not None
    except sqlite3.OperationalError:
        # Table pas encore créée (première exécution) : scheduler_control.add s'en chargera.
        return False


def ensure_curator_scheduled() -> None:
    """Enregistre la tâche planifiée quotidienne du curator via le scheduler."""
    if not settings.CURATOR_ENABLED:
        return
    try:
        if not _curator_already_scheduled():
            from tools.utils.scheduler_tools import scheduler_control

            scheduler_control(
                action="add",
                instruction=_CURATOR_INSTRUCTION,
                schedule_type="daily",
                time_of_day=settings.CURATOR_TIME,
            )
    except Exception as e:
        print(f"⚠️ [curator] Échec de la planification automatique : {e}")
