"""Agent unique de Monika."""

from config import SYSTEM_PROMPT
from agents.runtime import run_react_loop
from memory.manager import memory_manager, prompt_section
from tools.registry import AVAILABLE_TOOLS, TOOLS_SCHEMA

MAX_TURNS = 100

AGENT_SYSTEM_PROMPT = (
    SYSTEM_PROMPT + " "
    "Tu disposes directement de tous les outils nécessaires (système, fichiers, e-mails, "
    "calendrier, WhatsApp, contacts, recherche web, météo, Spotify, tâches planifiées et "
    "rappels, etc.). Utilise-les "
    "directement dès que c'est pertinent, sans jamais mentionner leur existence ni ta "
    "façon de procéder, et réponds toujours en français de façon concise.\n\n"
    "SCÉNARIO DE RÉSERVATION WEB (restaurant, rendez-vous...) via browser_control : pour "
    "aller jusqu'au bout d'une réservation réelle (pas seulement naviguer/cliquer), le "
    "déroulé typique est : naviguer vers le site -> list_interactive_elements pour repérer "
    "le formulaire de recherche de créneaux -> fill_field / select_option pour date, heure, "
    "nombre de personnes ou motif -> wait_for si les créneaux se chargent en AJAX -> "
    "click_element sur le créneau choisi -> fill_field pour les coordonnées de contact -> "
    "AVANT de cliquer sur le bouton final de validation/paiement, récapituler à "
    "l'utilisateur ce qui va être réservé (date, heure, nombre de personnes/motif, "
    "coordonnées utilisées, prix éventuel) et obtenir sa confirmation explicite, SAUF si "
    "l'utilisateur avait déjà donné ces informations précises dans sa demande initiale -> "
    "click_element sur le bouton de validation -> lire la page de confirmation "
    "(read_page_content) pour en extraire le numéro/texte de confirmation et le communiquer "
    "à l'utilisateur. Ne saisis JAMAIS "
    "d'informations de paiement (numéro de carte bancaire...) sans confirmation explicite de "
    "l'utilisateur pour cette réservation précise."
) + prompt_section()

# Contextes situationnels passés via process_user_message(context=...).
# Partagés pour éviter deux formulations jumelles qui divergent avec le temps.

SCHEDULED_TASK_CONTEXT = (
    "Contexte : l'échéance d'une tâche planifiée précédemment vient d'arriver. "
    "Aucun utilisateur n'est présent dans cette conversation pour répondre. "
    "Exécute l'instruction ci-dessous MAINTENANT, directement avec les outils "
    "nécessaires pour l'accomplir (ex: send_whatsapp_message, email_control, "
    "get_weather...). N'appelle PAS scheduler_control : la planification est déjà "
    "faite, il s'agit maintenant de l'exécuter réellement, pas de la reporter."
)


def process_user_message(
    messages: list,
    max_turns: int = MAX_TURNS,
    interactive: bool = True,
    context: str = "",
) -> str:
    """Traite le message de l'utilisateur avec un unique agent doté de tous les outils.

    `context` permet à l'appelant (tâche planifiée...) d'ajouter des
    consignes situationnelles au prompt système sans que celles-ci soient écrasées : elles sont
    concaténées à AGENT_SYSTEM_PROMPT plutôt que de le remplacer, ou l'inverse.
    """
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "system":
            del messages[i]

    system_content = AGENT_SYSTEM_PROMPT
    if context.strip():
        system_content = f"{AGENT_SYSTEM_PROMPT} {context.strip()}"

    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": system_content})
    else:
        messages[0]["content"] = system_content

    # Mémoire rapide : les souvenirs pertinents sont ajoutés au message de l'utilisateur POUR CE TOUR
    # seulement, puis retirés. Les mettre dans le prompt système le ferait changer à chaque tour, ce qui
    # invaliderait le cache de préfixe du serveur LLM sur tout l'historique ; et ils s'empileraient dans
    # la conversation s'ils y restaient.
    user_message = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    user_text = user_message.get("content") if user_message else None
    if not isinstance(user_text, str):
        user_text = ""  # contenu absent ou multimodal : on n'y touche pas

    memory_block = memory_manager.build_context(user_text) if user_text else ""
    if memory_block:
        user_message["content"] = user_text + memory_block
    try:
        reply = run_react_loop(
            messages,
            TOOLS_SCHEMA,
            AVAILABLE_TOOLS,
            max_turns=max_turns,
            interactive=interactive,
        )
    finally:
        if memory_block:
            user_message["content"] = user_text

    # Capture automatique (en arrière-plan) : seulement pour de vrais échanges avec l'utilisateur. Une tâche
    # planifiée qui boucle toutes les heures noierait la mémoire, et un message d'erreur n'a rien à retenir.
    if interactive and user_text and not reply.startswith("⚠️"):
        memory_manager.remember_turn(user_text, reply)
    return reply