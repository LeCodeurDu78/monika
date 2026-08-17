"""
tools/registry.py
------------------
Registre unique des outils de Monika.

Avant : les outils étaient déclarés à deux endroits différents (la fonction
Python dans registry.py, son schéma JSON dans schemas.py), avec un import
qui déclenchait des effets de bord entre les deux fichiers. Les deux listes
pouvaient diverger silencieusement (un outil renommé ou supprimé d'un côté,
oublié de l'autre).

Maintenant : chaque outil est décrit une seule fois, ici, sous la forme
(fonction Python exécutable, schéma JSON décrit au modèle). `AVAILABLE_TOOLS`
et `TOOLS_SCHEMA` sont deux vues issues de ce même registre.

Les outils "custom" créés à la volée par Monika (via create_custom_tool) sont
chargés dynamiquement depuis tools/custom/ et injectés dans les deux mêmes
structures par `sync_custom_tools`.
"""

import importlib
import inspect
import os
import sys

from tools.system.system_tools import open_application, system_control, get_system_stats
from tools.utils.weather_tools import get_weather
from tools.system.file_tools import manage_files
from tools.social.email_tools import email_control
from tools.system.search_tools import web_search
from tools.social.calendar_tools import calendar_control
from tools.utils.project_tools import create_full_project
from tools.system.terminal_tools import run_script
from tools.memory import memory_control
from tools.system.vision_tools import analyze_image
from tools.meta_tools import create_custom_tool
from tools.utils.joke_tools import get_joke
from tools.utils.spotify_tools import spotify_control
from tools.social.whatsapp_tools import send_whatsapp_message
from tools.social.contact_tools import manage_contacts
from tools.utils.reminder_tools import reminder_control
from tools.system.scheduler_tools import scheduler_control


def _schema(name: str, description: str, properties: dict, required: list | None = None) -> dict:
    """Construit un schéma de function calling au format attendu par l'API OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


# Registre de base : nom de l'outil -> fonction Python exécutable.
AVAILABLE_TOOLS = {
    "open_application": open_application,
    "get_weather": get_weather,
    "manage_files": manage_files,
    "system_control": system_control,
    "email_control": email_control,
    "web_search": web_search,
    "get_system_stats": get_system_stats,
    "calendar_control": calendar_control,
    "create_full_project": create_full_project,
    "run_script": run_script,
    "memory_control": memory_control,
    "analyze_image": analyze_image,
    "create_custom_tool": create_custom_tool,
    "get_joke": get_joke,
    "spotify_control": spotify_control,
    "send_whatsapp_message": send_whatsapp_message,
    "manage_contacts": manage_contacts,
    "reminder_control": reminder_control,
    "scheduler_control": scheduler_control,
}

# Schémas fournis au modèle pour le function calling, un par outil de base.
TOOLS_SCHEMA = [
    _schema(
        "open_application",
        "Ouvre une application installée sur l'ordinateur de l'utilisateur.",
        {"app_name": {"type": "string", "description": "Le nom de l'application (ex: notepad, chrome, calc)"}},
        ["app_name"],
    ),
    _schema(
        "get_weather",
        "Obtient la météo actuelle pour une ville donnée.",
        {"city": {"type": "string", "description": "Le nom de la ville (ex: Paris, Lyon, Montreal)"}},
        ["city"],
    ),
    _schema(
        "manage_files",
        "Liste, crée des dossiers ou déplace des fichiers sur l'ordinateur.",
        {
            "action": {"type": "string", "enum": ["list", "create_dir", "move"], "description": "L'action à effectuer"},
            "path": {"type": "string", "description": "Le chemin du fichier ou dossier à cibler"},
            "target_folder": {"type": "string", "description": "Le dossier de destination (nécessaire uniquement si action='move')"},
        },
        ["action", "path"],
    ),
    _schema(
        "system_control",
        "Contrôle les fonctionnalités du système Linux (volume, média, capture d'écran).",
        {
            "action": {
                "type": "string",
                "enum": ["volume_up", "volume_down", "screenshot", "media_toggle"],
                "description": "L'action système à exécuter.",
            },
            "value": {
                "type": "integer",
                "description": "Pourcentage de variation du volume. Utilisé uniquement pour volume_up/volume_down.",
            },
        },
        # NB: 'value' n'est requis que pour le volume (la fonction a un défaut de 5 pour
        # les autres actions) — le rendre obligatoire pour toutes les actions forçait le
        # modèle à inventer une valeur même pour 'screenshot' ou 'media_toggle'.
        ["action"],
    ),
    _schema(
        "email_control",
        "Permet de lire les derniers e-mails de la boîte de réception ou d'en envoyer un nouveau.",
        {
            "action": {"type": "string", "enum": ["list", "send"], "description": "'list' pour afficher les derniers messages, 'send' pour en envoyer un."},
            "recipient": {"type": "string", "description": "Adresse e-mail du destinataire (requis si action='send')."},
            "subject": {"type": "string", "description": "Sujet de l'e-mail (requis si action='send')."},
            "body": {"type": "string", "description": "Contenu/Corps de l'e-mail (requis si action='send')."},
            "limit": {"type": "integer", "description": "Nombre de derniers e-mails à lire (par défaut 5)."},
        },
        ["action"],
    ),
    _schema(
        "web_search",
        "Effectue des recherches en ligne sur Wikipédia ou sur le Web pour trouver des informations récentes ou de la culture générale.",
        {
            "source": {
                "type": "string",
                "enum": ["wikipedia", "duckduckgo"],
                "description": "'wikipedia' pour de la culture générale ou des définitions, 'duckduckgo' pour de l'actualité ou des recherches Web générales.",
            },
            "query": {"type": "string", "description": "Les termes de la recherche."},
        },
        ["source", "query"],
    ),
    _schema(
        "get_system_stats",
        "Obtient les métriques d'utilisation en temps réel du système (CPU, RAM, Disque, Batterie).",
        {},
        [],
    ),
    _schema(
        "calendar_control",
        "Consulte la liste des événements ou ajoute un rendez-vous dans Google Calendar.",
        {
            "action": {"type": "string", "enum": ["list", "add"], "description": "'list' pour voir les prochains événements, 'add' pour en créer un nouveau."},
            "summary": {"type": "string", "description": "Titre du rendez-vous/événement (requis pour action='add')."},
            "start_time": {"type": "string", "description": "Date et heure de début au format ISO (ex: 2026-08-12T14:00:00)."},
            "end_time": {"type": "string", "description": "Date et heure de fin au format ISO (ex: 2026-08-12T15:00:00)."},
            "limit": {"type": "integer", "description": "Nombre d'événements à afficher (par défaut 5)."},
        },
        ["action"],
    ),
    _schema(
        "create_full_project",
        "Initialise un projet complet : crée le dossier dans Code, génère un dépôt GitHub et configure un Vault Obsidian.",
        {
            "project_name": {"type": "string", "description": "Le nom du projet (ex: monika-v2, api-backend, portfolio)"},
            "private": {"type": "boolean", "description": "True pour rendre le dépôt GitHub privé (par défaut), False pour public."},
        },
        ["project_name"],
    ),
    _schema(
        "run_script",
        "Exécute une commande ou un script Bash dans le terminal local.",
        {
            "command": {"type": "string", "description": "La commande Bash exacte à exécuter (ex: 'ls -la', 'python3 script.py', 'git status')."},
            "workdir": {"type": "string", "description": "Le dossier d'exécution de la commande (ex: '/home/adam/Documents/Code/monika')."},
        },
        ["command"],
    ),
    _schema(
        "memory_control",
        "Stocke ou recherche des informations importantes à long terme (préférences de l'utilisateur, chemins de projets, règles de code, faits personnels). La recherche ('search') est sémantique : elle retrouve les souvenirs par sens, pas seulement par mot-clé exact.",
        {
            "action": {"type": "string", "enum": ["save", "search", "list"], "description": "'save' pour enregistrer/mettre à jour une mémoire, 'search' pour chercher par sens/mot-clé, 'list' pour tout afficher."},
            "key": {"type": "string", "description": "Pour 'save' : clé d'identification (ex: 'editeur_prefere'). Pour 'search' : le texte de la requête (ex: 'éditeur de code')."},
            "value": {"type": "string", "description": "L'information exacte à retenir (requise si action='save')."},
            "category": {"type": "string", "description": "Catégorie facultative (ex: 'preferences', 'projets', 'regles')."},
        },
        ["action"],
    ),
    _schema(
        "analyze_image",
        "Analyse visuellement une image locale ou une capture d'écran (extraire du texte, lire des erreurs, décrire un schéma, identifier des éléments à l'écran).",
        {
            "image_path": {"type": "string", "description": "Le chemin du fichier image à analyser (ex: '/home/adam/Images/screenshot.png')."},
            "prompt": {"type": "string", "description": "Consigne précise sur ce que l'agent doit observer ou chercher dans l'image (ex: 'Que dit ce message d'erreur ?')."},
        },
        ["image_path"],
    ),
    _schema(
        "create_custom_tool",
        "Permet d'écrire et sauvegarder un nouvel outil Python réutilisable lorsque la demande nécessite une fonctionnalité inexistante.",
        {
            "tool_name": {"type": "string", "description": "Nom de la fonction Python en snake_case (ex: 'fetch_crypto_price')."},
            "python_code": {"type": "string", "description": "Code Python autonome complet définissant la fonction."},
            "description": {"type": "string", "description": "Explication de ce que fait la fonction et ses paramètres."},
        },
        ["tool_name", "python_code", "description"],
    ),
    _schema(
        "get_joke",
        "Raconte une blague amusante pour développeurs ou geeks.",
        {
            "language": {"type": "string", "description": "Langue de la blague ('fr', 'en', 'es', 'de'). Par défaut 'fr'."},
            "category": {"type": "string", "description": "Catégorie de blague ('neutral', 'chuck', 'all'). Par défaut 'neutral'."},
        },
        [],
    ),
    _schema(
        "spotify_control",
        "Permet de contrôler Spotify : lire de la musique, mettre en pause, passer un morceau, changer le volume ou chercher des playlists.",
        {
            "action": {
                "type": "string",
                "enum": ["play", "pause", "next", "previous", "rewind", "current", "volume"],
                "description": "L'action Spotify à exécuter.",
            },
            "query": {"type": "string", "description": "Le nom du morceau, de l'artiste ou de la playlist (pour action='play')."},
            "volume": {"type": "integer", "description": "Le niveau de volume de 0 à 100 (pour action='volume')."},
        },
        ["action"],
    ),
    _schema(
        "manage_contacts",
        "Gère le carnet d'adresses : ajouter, chercher, lister ou supprimer des contacts (Nom -> Numéro).",
        {
            "action": {"type": "string", "enum": ["add", "get", "list", "delete"], "description": "Action à effectuer sur les contacts."},
            "name": {"type": "string", "description": "Le nom du contact (ex: 'Adam', 'Maman')."},
            "phone_number": {"type": "string", "description": "Numéro au format international commençant par '+' (ex: '+33612345678')."},
        },
        ["action"],
    ),
    _schema(
        "send_whatsapp_message",
        "Envoie un message WhatsApp à un destinataire en utilisant soit son prénom/nom enregistrés, soit directement son numéro.",
        {
            "recipient": {"type": "string", "description": "Nom du contact dans le carnet d'adresses (ex: 'Adam', 'Maman') OU numéro au format '+33...'."},
            "message": {"type": "string", "description": "Le texte du message à envoyer."},
        },
        ["recipient", "message"],
    ),
    _schema(
        "reminder_control",
        "Crée, liste ou supprime des rappels avec échéance (ex: \"rappelle-moi de renouveler mon passeport avant le 20 mars\"). Un rappel arrivé à échéance est annoncé automatiquement par Monika, sans que l'utilisateur ait à demander.",
        {
            "action": {
                "type": "string",
                "enum": ["add", "list", "delete", "due"],
                "description": "'add' pour créer un rappel, 'list' pour voir les prochains rappels, 'delete' pour en supprimer un, 'due' pour voir ceux arrivés à échéance et pas encore annoncés.",
            },
            "message": {"type": "string", "description": "Le texte du rappel (requis pour action='add')."},
            "due_at": {"type": "string", "description": "Date et heure d'échéance au format ISO (ex: '2026-08-20T09:00:00'), requis pour action='add'."},
            "reminder_id": {"type": "integer", "description": "Identifiant du rappel à supprimer (requis pour action='delete', voir la liste via action='list')."},
            "limit": {"type": "integer", "description": "Nombre de rappels à afficher pour action='list' (par défaut 10)."},
        },
        ["action"],
    ),
    _schema(
        "scheduler_control",
        "Planifie l'exécution AUTONOME d'une instruction par Monika elle-même : contrairement à reminder_control qui se contente d'annoncer un message, ici Monika appelle réellement les outils nécessaires (météo, e-mails, recherche web...) pour accomplir la tâche, sans intervention de l'utilisateur. Une seule fois, tous les jours, ou en boucle à intervalle régulier.",
        {
            "action": {
                "type": "string",
                "enum": ["add", "list", "cancel"],
                "description": "'add' pour planifier une tâche, 'list' pour voir les tâches actives, 'cancel' pour en annuler une.",
            },
            "instruction": {"type": "string", "description": "Ce que Monika doit faire, en langage naturel (ex: 'donne la météo de Paris', 'vérifie mes derniers e-mails'). Requis pour action='add'."},
            "schedule_type": {
                "type": "string",
                "enum": ["once", "daily", "interval"],
                "description": "'once' pour une seule fois (avec 'run_at'), 'daily' pour tous les jours (avec 'time_of_day'), 'interval' pour une boucle récurrente (avec 'interval_seconds'). Requis pour action='add'.",
            },
            "run_at": {"type": "string", "description": "Date et heure ISO du déclenchement unique (ex: '2026-08-20T09:00:00'), requis si schedule_type='once'."},
            "time_of_day": {"type": "string", "description": "Heure quotidienne de déclenchement au format 'HH:MM' (ex: '08:00'), requis si schedule_type='daily'."},
            "interval_seconds": {"type": "integer", "description": "Période de répétition en secondes (ex: 3600 pour toutes les heures), requis si schedule_type='interval'."},
            "task_id": {"type": "integer", "description": "Identifiant de la tâche à annuler (requis pour action='cancel', voir action='list')."},
        },
        ["action"],
    ),
]


def _generate_schema_from_func(func, name: str, description: str) -> dict:
    """Génère automatiquement un schéma JSON à partir de la signature d'une fonction.

    Utilisé uniquement pour les outils "custom" écrits sans schéma explicite.
    """
    sig = inspect.signature(func)
    type_map = {int: "integer", float: "number", bool: "boolean"}
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        properties[param_name] = {
            "type": type_map.get(param.annotation, "string"),
            "description": f"Paramètre {param_name}",
        }
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return _schema(name, description, properties, required)


def sync_custom_tools(target_schema_list: list) -> None:
    """Parcourt le dossier tools/custom/, charge les fonctions Python dans AVAILABLE_TOOLS
    et injecte leurs schémas JSON dans `target_schema_list`.
    """
    custom_dir = os.path.join(os.path.dirname(__file__), "custom")
    if not os.path.exists(custom_dir):
        return

    if custom_dir not in sys.path:
        sys.path.append(custom_dir)

    for filename in os.listdir(custom_dir):
        if not filename.endswith(".py") or filename.startswith("__"):
            continue

        tool_name = filename[:-3]
        try:
            module_name = f"tools.custom.{tool_name}"
            module = (
                importlib.reload(sys.modules[module_name])
                if module_name in sys.modules
                else importlib.import_module(module_name)
            )

            func = getattr(module, tool_name, None)
            if func is None:
                continue

            # 1. Enregistrement de l'exécutable
            AVAILABLE_TOOLS[tool_name] = func

            # 2. Ajout au schéma si pas encore présent
            if not any(s["function"]["name"] == tool_name for s in target_schema_list):
                doc = (func.__doc__ or f"Outil personnalisé {tool_name}").strip()
                target_schema_list.append(_generate_schema_from_func(func, tool_name, doc))
                print(f"🧩 [Outil Personnalisé Chargé] : {tool_name}")
        except Exception as e:
            print(f"⚠️ Impossible de charger l'outil personnalisé {tool_name} : {e}")


sync_custom_tools(TOOLS_SCHEMA)
