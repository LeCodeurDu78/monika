"""Agent unique de Monika."""

from config import SYSTEM_PROMPT
from agents.runtime import run_react_loop
from tools.registry import AVAILABLE_TOOLS, TOOLS_SCHEMA

MAX_TURNS = 100

AGENT_SYSTEM_PROMPT = (
    SYSTEM_PROMPT + " "
    "Tu disposes directement de tous les outils nécessaires (système, fichiers, e-mails, "
    "calendrier, WhatsApp, contacts, recherche web, mémoire long terme, RAG, graphe de "
    "connaissances, météo, Spotify, rappels, tâches planifiées, etc.). Utilise-les "
    "directement dès que c'est pertinent, sans jamais mentionner leur existence ni ta "
    "façon de procéder, et réponds toujours en français de façon concise."
)


def process_user_message(messages: list, max_turns: int = MAX_TURNS, interactive: bool = True) -> str:
    """Traite le message de l'utilisateur avec un unique agent doté de tous les outils."""
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": AGENT_SYSTEM_PROMPT})
    else:
        messages[0]["content"] = AGENT_SYSTEM_PROMPT

    return run_react_loop(
        messages,
        TOOLS_SCHEMA,
        AVAILABLE_TOOLS,
        max_turns=max_turns,
        interactive=interactive,
    )
