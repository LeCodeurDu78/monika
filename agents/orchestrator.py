"""Agent unique de Monika."""

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from config import build_persona_prompt
from agents.runtime import run_react_loop
from core.serial_executor import SerialExecutor
from core.settings import settings
from memory.manager import memory_manager, prompt_section
from tools.registry import AVAILABLE_TOOLS, TOOLS_SCHEMA, TOOL_DEFS_BY_NAME
from tools.guides import GUIDES

MAX_TURNS = 100

_AGENT_THREAD = SerialExecutor("monika-agent")

_TOOLS_NOTE = (
    "## Outils\n"
    "Tu disposes d'outils (système, fichiers, e-mails, calendrier, Discord, recherche web, météo, "
    "Spotify, rappels et tâches planifiées...). Utilise-les directement dès que c'est pertinent. "
    "Ne parle pas de tes outils dans tes réponses, sauf si on te demande ce que tu sais faire."
)

# Contextes situationnels passés via process_user_message(context=...).
# Partagés pour éviter deux formulations jumelles qui divergent avec le temps.

SCHEDULED_TASK_CONTEXT = (
    "Contexte : l'échéance d'une tâche planifiée précédemment vient d'arriver. "
    "Aucun utilisateur n'est présent dans cette conversation pour répondre. "
    "Exécute l'instruction ci-dessous MAINTENANT, directement avec les outils "
    "nécessaires pour l'accomplir (ex: send_discord_message, email_control, "
    "get_weather...). N'appelle PAS scheduler_control : la planification est déjà "
    "faite, il s'agit maintenant de l'exécuter réellement, pas de la reporter."
)

DISCORD_CONTEXT = (
    "Contexte : l'utilisateur te parle par Discord (message privé ou salon), probablement loin de son "
    "ordinateur. Ta réponse lui est envoyée automatiquement sur Discord : n'appelle donc PAS "
    "send_discord_message pour lui répondre. Reste concis ; le Markdown Discord (**gras**, `code`, "
    "listes) est accepté, évite les tableaux. Les messages Discord sont limités à 2000 caractères "
    "(le surplus est envoyé en plusieurs messages)."
)

_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def _now() -> datetime:
    try:
        return datetime.now(ZoneInfo(settings.TIMEZONE))
    except Exception:  # fuseau inconnu ou base tz absente : heure locale de la machine
        return datetime.now().astimezone()


def _environment_block(now: datetime) -> str:
    """Date, fuseau et système : sans eux, le modèle invente les dates (« demain », rappels, agenda).

    Seule la date figure ici (elle ne change qu'une fois par jour, ce qui préserve le cache de préfixe
    du serveur LLM) ; l'heure exacte est ajoutée à chaque message de l'utilisateur.
    """
    date_fr = f"{_JOURS[now.weekday()]} {now.day} {_MOIS[now.month - 1]} {now.year}"
    return (
        "## Contexte\n"
        f"- Date du jour : {date_fr}.\n"
        f"- Fuseau horaire : {settings.TIMEZONE}. L'heure exacte est indiquée à la fin de chaque message de l'utilisateur.\n"
        f"- Système : Linux. Dossier personnel : {Path.home()}."
    )


def build_system_prompt(voice: bool, context: str = "") -> str:
    parts = [
        build_persona_prompt(voice=voice),
        _environment_block(_now()),
        _TOOLS_NOTE,
        prompt_section().strip(),
    ]
    parts.extend(GUIDES)
    if context.strip():
        parts.append(context.strip())
    return "\n\n".join(part for part in parts if part)


def process_user_message(
    messages: list,
    max_turns: int = MAX_TURNS,
    interactive: bool = True,
    context: str = "",
    voice: bool = False,
    on_wait: Optional[Callable[[str], None]] = None,
) -> str:
    """Traite le message de l'utilisateur avec un unique agent (voir `_process_user_message`).

    Tous les tours (clavier, tâches planifiées, Discord) passent par un même thread dédié : voir
    core/serial_executor.py. `on_wait(phrase)` est appelé (depuis un autre thread) quand un outil marqué
    `lent` prend du temps : l'appelant dit la phrase sur son canal (voix, terminal, Discord...).
    """
    return _AGENT_THREAD.run(_process_user_message, messages, max_turns, interactive, context, voice, on_wait)


def _process_user_message(
    messages: list,
    max_turns: int = MAX_TURNS,
    interactive: bool = True,
    context: str = "",
    voice: bool = False,
    on_wait: Optional[Callable[[str], None]] = None,
) -> str:
    """Traite le message de l'utilisateur avec un unique agent.

    `context` permet à l'appelant (tâche planifiée...) d'ajouter des consignes situationnelles
    au prompt système. `voice` choisit le style de réponse (oral et concis, ou texte développé).
    """
    # Le raisonnement des tours précédents ne doit pas être renvoyé au modèle.
    for msg in messages:
        msg.pop("reasoning_content", None)

    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "system":
            del messages[i]

    user_message = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    user_text = user_message.get("content") if user_message else None
    if not isinstance(user_text, str):
        user_text = ""  # contenu absent ou multimodal : on n'y touche pas

    system_content = build_system_prompt(voice, context)

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_content})
    else:
        messages[0]["content"] = system_content

    # Ajouts valables POUR CE TOUR seulement, puis retirés : l'heure exacte et la mémoire rapide.
    # Les mettre dans le prompt système le ferait changer à chaque tour (cache de préfixe du serveur
    # LLM invalidé sur tout l'historique) ; et ils s'empileraient dans la conversation s'ils y restaient.
    turn_addendum = ""
    if user_text:
        turn_addendum = f"\n\n[Heure actuelle : {_now():%H:%M}]" + memory_manager.build_context(user_text)
        user_message["content"] = user_text + turn_addendum
    try:
        reply = run_react_loop(
            messages,
            # Tous les outils sont exposés. Les deux structures sont celles du registre (pas des copies) :
            # un outil créé en cours de tour par create_custom_tool est utilisable tout de suite.
            lambda: TOOLS_SCHEMA,
            AVAILABLE_TOOLS,
            max_turns=max_turns,
            interactive=interactive,
            tool_defs=TOOL_DEFS_BY_NAME,
            on_wait=on_wait,
        )
    finally:
        if turn_addendum:
            user_message["content"] = user_text

    # Capture automatique (en arrière-plan) : seulement pour de vrais échanges avec l'utilisateur. Une tâche
    # planifiée qui boucle toutes les heures noierait la mémoire, et un message d'erreur n'a rien à retenir.
    if interactive and user_text and not reply.startswith("⚠️"):
        memory_manager.remember_turn(user_text, reply)
    return reply
