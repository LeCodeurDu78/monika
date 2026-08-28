"""Briefing du matin : résumé de la veille (mémoire long terme + rappels/tâches à venir), météo
(ville récupérée depuis la mémoire long terme, pas depuis une config figée), actualités, et
nouveautés sur les sujets surveillés (tools/utils/topic_tools.py) — le tout en UN seul envoi
quotidien, déclenché au premier lancement de la journée."""

from datetime import datetime

from config import SYSTEM_PROMPT
from tools.utils.topic_tools import check_watched_topics


def _build_instruction() -> str:
    return (
        f"Prépare mon briefing du matin du {datetime.now().strftime('%d/%m/%Y')}, en parties courtes "
        f"et clairement séparées :\n"
        f"1) Résumé de la veille : ce qui est pertinent aujourd'hui d'après ma mémoire long terme "
        f"(memory_control) et mes rappels/tâches à venir (reminder_control, scheduler_control).\n"
        f"2) Météo du jour : cherche d'abord dans ma mémoire long terme (memory_control, action='search') "
        f"la ville où j'habite (ex: requête 'ville', 'domicile', 'où j'habite'), puis appelle get_weather "
        f"avec cette ville. Si aucune ville n'est trouvée en mémoire, ignore cette section et signale-le "
        f"brièvement en me demandant de te dire où j'habite pour la prochaine fois.\n"
        f"3) Actualités principales du jour (web_search avec source='duckduckgo').\n"
        f"Réponds en français, de façon concise, avec des titres de section courts."
    )


def run_morning_briefing() -> str:
    """Compose et exécute le briefing du matin (mémoire, rappels, météo, actus) et y intègre les
    nouveautés détectées sur les sujets surveillés, dans un seul message."""
    from agents.orchestrator import process_user_message

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_instruction()},
    ]
    try:
        briefing = process_user_message(messages, interactive=False)
    except Exception as e:
        briefing = f"⚠️ Échec de la préparation du briefing du matin : {e}"

    topic_alerts = check_watched_topics()
    if topic_alerts:
        briefing = f"{briefing}\n\n🔎 Veille de sujets :\n{topic_alerts}"

    return briefing
