"""Définition des agents spécialisés de Monika."""

from tools.registry import AVAILABLE_TOOLS, TOOLS_SCHEMA


def _subset(tool_names: list[str]) -> tuple[dict, list]:
    """Extrait, à partir du registre global, le dictionnaire de fonctions et le schéma JSON correspondant à `tool_names`."""
    tools = {name: AVAILABLE_TOOLS[name] for name in tool_names if name in AVAILABLE_TOOLS}
    schema = [s for s in TOOLS_SCHEMA if s["function"]["name"] in tools]
    return tools, schema


class Specialist:
    """Un agent spécialisé : un domaine, un system prompt, un sous-ensemble d'outils."""

    def __init__(self, name: str, label: str, description: str, system_prompt: str, tool_names: list[str]):
        self.name = name
        self.label = label
        self.description = description
        self.system_prompt = system_prompt
        self.tools, self.tools_schema = _subset(tool_names)


_SYSTEM_TOOL_NAMES = [
    "open_application",
    "manage_files",
    "system_control",
    "get_system_stats",
    "run_script",
    "analyze_image",
    "create_full_project",
    "get_screen_context",
    "browser_control",
]

_SOCIAL_TOOL_NAMES = [
    "email_control",
    "calendar_control",
    "send_whatsapp_message",
    "manage_contacts",
]

_KNOWLEDGE_TOOL_NAMES = [
    "web_search",
    "memory_control",
    "rag_control",
    "graph_search",
    "graph_backfill",
]

_PRODUCTIVITY_TOOL_NAMES = [
    "get_weather",
    "spotify_control",
    "get_joke",
    "reminder_control",
    "scheduler_control",
    "create_custom_tool",
    "patch_existing_file",
    "behavior_control",
    "proactive_control",
]

_assigned = set(_SYSTEM_TOOL_NAMES + _SOCIAL_TOOL_NAMES + _KNOWLEDGE_TOOL_NAMES + _PRODUCTIVITY_TOOL_NAMES)
_CUSTOM_TOOL_NAMES = [name for name in AVAILABLE_TOOLS if name not in _assigned]
_PRODUCTIVITY_TOOL_NAMES = _PRODUCTIVITY_TOOL_NAMES + _CUSTOM_TOOL_NAMES


SPECIALISTS: dict[str, Specialist] = {
    "system": Specialist(
        name="system",
        label="Agent Système",
        description=(
            "Actions concrètes sur l'ordinateur : ouvrir des applications, gérer des fichiers/dossiers, "
            "contrôler le système (volume, capture d'écran, média), lancer des commandes/scripts, "
            "analyser des images/captures d'écran, obtenir le contexte structuré de l'écran actif "
            "(app, fenêtre, texte OCR), initialiser des projets complets (code + GitHub + Obsidian), "
            "contrôler un navigateur Firefox géré par Monika elle-même (onglets, navigation, lecture de "
            "page, clic/remplissage de champs — aucun navigateur déjà ouvert requis)."
        ),
        system_prompt=(
            "Tu es l'agent Système de Monika. Tu exécutes des actions concrètes sur l'ordinateur de "
            "l'utilisateur : fichiers, applications, terminal, projets, images, contexte d'écran, navigateur "
            "(browser_control : Monika lance et gère elle-même un Firefox dédié au premier besoin, c'est "
            "une fenêtre distincte du navigateur personnel de l'utilisateur — précise-le si on te demande "
            "d'agir sur 'le' navigateur). Utilise "
            "directement les outils à ta disposition, sans demander de confirmation superflue. Réponds en une "
            "phrase claire et concise confirmant ce qui a été fait ou constaté."
        ),
        tool_names=_SYSTEM_TOOL_NAMES,
    ),
    "social": Specialist(
        name="social",
        label="Agent Social",
        description=(
            "Communication et organisation sociale : e-mails (lire/envoyer), calendrier (consulter/ajouter), "
            "messages WhatsApp, carnet de contacts."
        ),
        system_prompt=(
            "Tu es l'agent Social de Monika. Tu gères les e-mails, le calendrier, les messages WhatsApp et le "
            "carnet de contacts de l'utilisateur. Sois précis sur les destinataires et les dates/heures. "
            "Réponds en rapportant clairement ce qui a été envoyé, trouvé ou planifié."
        ),
        tool_names=_SOCIAL_TOOL_NAMES,
    ),
    "knowledge": Specialist(
        name="knowledge",
        label="Agent Connaissances",
        description=(
            "Recherche et mémoire : recherche web (Wikipédia/DuckDuckGo), mémoire long terme de l'utilisateur, "
            "RAG sur documents personnels indexés, graphe de connaissances relationnel."
        ),
        system_prompt=(
            "Tu es l'agent Connaissances de Monika. Tu recherches des informations sur le web, dans la mémoire "
            "long terme et dans les documents indexés (RAG/graphe de connaissances). Synthétise clairement les "
            "résultats trouvés, cite tes sources quand elles sont disponibles, et signale si rien de pertinent "
            "n'a été trouvé plutôt que d'inventer une réponse."
        ),
        tool_names=_KNOWLEDGE_TOOL_NAMES,
    ),
    "productivity": Specialist(
        name="productivity",
        label="Agent Productivité",
        description=(
            "Vie quotidienne et automatisation : météo, Spotify, blagues, rappels avec échéance, tâches "
            "planifiées exécutées de façon autonome, création de nouveaux outils personnalisés, consultation/"
            "réinitialisation du journal comportemental, contrôle du mode silencieux des interventions "
            "autonomes, et tout outil personnalisé déjà créé par l'utilisateur. Peut aussi patcher un fichier "
            "existant du projet Monika (patch_existing_file) quand une modification de code va au-delà de la "
            "création d'un outil isolé."
        ),
        system_prompt=(
            "Tu es l'agent Productivité de Monika. Tu gères la météo, Spotify, les blagues, les rappels, les "
            "tâches planifiées, le journal comportemental (behavior_control), le mode silencieux des "
            "interventions autonomes (proactive_control) et les outils personnalisés créés par l'utilisateur "
            "(ainsi que la création de nouveaux outils via create_custom_tool si aucun outil existant ne "
            "convient, ou le patch d'un fichier existant via patch_existing_file si la demande porte "
            "explicitement sur une modification du code de Monika elle-même — utilise-le avec prudence, "
            "uniquement quand l'utilisateur demande clairement une modification de son propre code). Sois "
            "concis et confirme précisément ce qui a été fait ou programmé."
        ),
        tool_names=_PRODUCTIVITY_TOOL_NAMES,
    ),
}
