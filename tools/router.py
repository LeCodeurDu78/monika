"""Sélection des outils exposés au modèle selon la demande.

Envoyer ~20 outils aux descriptions longues à chaque appel noie les petits modèles. Ici, un
noyau d'outils reste toujours disponible, et les autres sont ajoutés par groupe quand la demande
(ou l'historique récent) s'y rapporte. Si le modèle a besoin d'un groupe absent, il l'active
lui-même avec l'outil `enable_tools`. Les outils inconnus de ce fichier (outils personnalisés,
créés à la volée) sont toujours fournis.
"""

import re
import unicodedata
from typing import Callable, Iterable

CORE = "core"

TOOL_GROUP: dict[str, str] = {
    # noyau, toujours disponible
    "web_search": CORE,
    "run_script": CORE,
    "manage_files": CORE,
    "open_application": CORE,
    "get_system_stats": CORE,
    "scheduler_control": CORE,
    "user_memory": CORE,
    "deep_memory": CORE,
    # groupes à la demande
    "browser_control": "browser",
    "email_control": "mail",
    "calendar_control": "calendar",
    "send_whatsapp_message": "social",
    "manage_contacts": "social",
    "spotify_control": "spotify",
    "system_control": "system",
    "analyze_image": "system",
    "get_weather": "weather",
    "create_full_project": "dev",
    "create_custom_tool": "dev",
    "patch_existing_file": "dev",
}

GROUP_LABELS = {
    "browser": "navigateur web (sites, formulaires, réservations)",
    "mail": "e-mails",
    "calendar": "agenda Google Calendar",
    "social": "WhatsApp et carnet de contacts",
    "spotify": "Spotify",
    "system": "volume, capture d'écran, analyse d'image",
    "weather": "météo",
    "dev": "projets, création d'outils, modification du code de Monika",
}

# Mots-clés (texte normalisé : minuscules, sans accents).
_KEYWORDS: dict[str, str] = {
    "browser": r"site|navigu|naviguer|page web|url|https?:|www\.|\.com|\.fr|onglet|navigateur|firefox|formulaire|reserv|clique|connecte-toi|se connecter",
    "mail": r"mail|courriel|courrier|boite de reception|inbox|gmail",
    "calendar": r"agenda|calendrier|calendar|rendez-vous|rdv|reunion|evenement|planning|emploi du temps|\bcours\b",
    "social": r"whatsapp|contact|numero|\bsms\b|annuaire|carnet",
    "spotify": r"spotify|musique|morceau|chanson|playlist|artiste|album|\bjoue\b|pause|suivant|precedent",
    "system": r"volume|\bson\b|capture|ecran|screenshot|screen|image|photo|\bpng\b|jpe?g|schema|lecture",
    "weather": r"meteo|quel temps|le temps|pluie|pleut|soleil|temperature|il fait|neige|vent\b|orage|parapluie",
    "dev": r"projet|repo|github|depot|vault|obsidian|\boutil|\btool|patch|code de monika|fonctionnalite|modifie.*(code|monika|\.py)",
}
_PATTERNS = {group: re.compile(rx) for group, rx in _KEYWORDS.items()}

_RECENT_USER_MESSAGES = 3

ENABLE_TOOLS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "enable_tools",
        "description": (
            "Active des outils supplémentaires quand celui dont tu as besoin n'est pas dans ta liste. "
            "Groupes : " + " ; ".join(f"{name} ({label})" for name, label in GROUP_LABELS.items()) + "."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "groups": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(GROUP_LABELS)},
                    "description": "Les groupes à activer.",
                }
            },
            "required": ["groups"],
        },
    },
}

# Consignes détaillées, chargées seulement quand le groupe est actif (au lieu d'alourdir chaque prompt).
GROUP_GUIDES: dict[str, str] = {
    "browser": (
        "## Réservation web (restaurant, rendez-vous...) avec browser_control\n"
        "Déroulé : naviguer vers le site -> list_interactive_elements pour repérer le formulaire -> "
        "fill_field / select_option pour date, heure, nombre de personnes ou motif -> wait_for si les "
        "créneaux se chargent en AJAX -> click_element sur le créneau -> fill_field pour les coordonnées -> "
        "AVANT le bouton final de validation ou de paiement, récapituler (date, heure, personnes/motif, "
        "coordonnées, prix) et obtenir la confirmation explicite de l'utilisateur, sauf s'il avait déjà "
        "donné ces informations précises dans sa demande -> click_element sur la validation -> "
        "read_page_content pour relever le numéro ou texte de confirmation et le communiquer. "
        "Ne saisis JAMAIS d'informations de paiement sans confirmation explicite pour cette réservation précise."
    ),
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def group_of(tool_name: str) -> str:
    """Groupe d'un outil ; les outils inconnus (personnalisés) sont traités comme du noyau."""
    return TOOL_GROUP.get(tool_name, CORE)


def select_groups(messages: list, user_text: str = "") -> set[str]:
    """Groupes d'outils à exposer : noyau + groupes évoqués récemment + groupes déjà utilisés."""
    active = {CORE}

    texts = [user_text] if user_text else []
    seen = 0
    for msg in reversed(messages):
        if seen >= _RECENT_USER_MESSAGES:
            break
        if msg.get("role") == "user" and isinstance(msg.get("content"), str):
            texts.append(msg["content"])
            seen += 1
    haystack = _normalize("\n".join(texts))
    for group, pattern in _PATTERNS.items():
        if pattern.search(haystack):
            active.add(group)

    # Un groupe déjà utilisé dans la conversation reste disponible (suite d'un échange).
    for msg in messages:
        for call in msg.get("tool_calls") or []:
            name = call.get("function", {}).get("name", "")
            group = group_of(name)
            if group != CORE:
                active.add(group)
    return active


def build_schema(all_schemas: Iterable[dict], active: set[str]) -> list[dict]:
    """Schémas des outils des groupes actifs, plus enable_tools s'il reste des groupes à activer."""
    schemas = [s for s in all_schemas if group_of(s["function"]["name"]) in active]
    if any(g not in active for g in GROUP_LABELS):
        schemas.append(ENABLE_TOOLS_SCHEMA)
    return schemas


def make_enable_tools(active: set[str]) -> Callable[..., str]:
    """Fabrique l'outil enable_tools lié à l'ensemble `active` de l'appel en cours."""

    def enable_tools(groups=None) -> str:
        if isinstance(groups, str):
            groups = [groups]
        groups = list(groups or [])
        unknown = [g for g in groups if g not in GROUP_LABELS]
        valid = [g for g in groups if g in GROUP_LABELS]
        if not valid:
            return "❌ Aucun groupe valide. Groupes possibles : " + ", ".join(GROUP_LABELS) + "."
        names = sorted({n for n, g in TOOL_GROUP.items() if g in valid})
        newly = [g for g in valid if g not in active]
        active.update(valid)
        parts = ["✅ Outils activés : " + ", ".join(names) + ". Tu peux les appeler maintenant."]
        if unknown:
            parts.append("Groupes ignorés (inconnus) : " + ", ".join(unknown) + ".")
        for group in newly:
            guide = GROUP_GUIDES.get(group)
            if guide:
                parts.append(guide)
        return "\n\n".join(parts)

    return enable_tools
