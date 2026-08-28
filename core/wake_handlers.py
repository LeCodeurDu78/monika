"""Logique exécutée lors d'un réveil ponctuel par le planificateur natif de l'OS."""

from config import SYSTEM_PROMPT
from core.wake_store import mark_ran_today, push_wake_result as push_outbox, should_run_today


def handle_wake(kind: str, ref_id: int) -> None:
    """Point d'entrée unique, dispatché par type de réveil."""
    try:
        if kind == "reminder":
            _handle_reminder(ref_id)
        elif kind == "task":
            _handle_task(ref_id)
        elif kind == "briefing":
            _handle_briefing()
        else:
            print(f"⚠️ [wake] Type de réveil non reconnu : '{kind}'.")
    except Exception as e:
        print(f"⚠️ [wake] Échec du réveil natif ('{kind}', id={ref_id}) : {e}")


def _handle_reminder(reminder_id: int) -> None:
    from tools.utils.reminder_tools import reminder_control

    due_text = reminder_control("due")
    if due_text:
        push_outbox("reminder", due_text)


def _handle_task(task_id: int) -> None:
    from agents.orchestrator import process_user_message
    from tools.utils.scheduler_tools import pop_due_tasks

    for tid, instruction in pop_due_tasks():
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    "Contexte : l'échéance d'une tâche planifiée précédemment vient d'arriver, et le "
                    "process principal de Monika n'était pas actif — tu as été relancée ponctuellement "
                    "par le planificateur natif de l'OS, uniquement pour exécuter cette tâche. Utilise "
                    "directement les outils nécessaires (météo, e-mails, recherche web, WhatsApp...) "
                    "pour l'accomplir MAINTENANT, sans intervention de l'utilisateur, puis termine. "
                    "N'appelle PAS scheduler_control : la planification est déjà faite."
                ),
            },
            {"role": "user", "content": instruction},
        ]
        try:
            result = process_user_message(messages, interactive=False)
        except Exception as e:
            result = f"⚠️ Échec de la tâche planifiée #{tid} : {e}"
        push_outbox("task", f"[Tâche #{tid}] {instruction}\n→ {result}")


def _handle_briefing() -> None:
    """Briefing du matin — inclut désormais la veille de sujets dans le même envoi
    (voir tools/utils/briefing_tools.py)."""
    if not should_run_today("morning_briefing"):
        return
    mark_ran_today("morning_briefing")

    from tools.utils.briefing_tools import run_morning_briefing

    result = run_morning_briefing()
    if result:
        push_outbox("briefing", result)
