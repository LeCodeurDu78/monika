"""Registre unique des outils de Monika : chaque outil est décrit une seule fois."""

import importlib
import inspect
import os
import sys

from tools.system.system_tools import open_application, system_control, get_system_stats
from tools.utils.weather_tools import get_weather
from tools.system.file_tools import manage_files
from tools.social.email_tools import email_control
from tools.utils.search_tools import web_search
from tools.social.calendar_tools import calendar_control
from tools.utils.project_tools import create_full_project
from tools.system.terminal_tools import run_script
from tools.knowledge.memory import memory_control
from tools.knowledge.rag_tools import rag_control
from tools.knowledge.graph_rag import graph_search, graph_backfill
from tools.vision.vision_tools import analyze_image
from tools.meta_tools import create_custom_tool, patch_existing_file
from tools.system.browser_control import browser_control
from tools.utils.joke_tools import get_joke
from tools.utils.spotify_tools import spotify_control
from tools.social.whatsapp_tools import send_whatsapp_message
from tools.social.contact_tools import manage_contacts
from tools.utils.reminder_tools import reminder_control
from tools.utils.scheduler_tools import scheduler_control
from tools.system.screen_context import get_screen_context
from tools.system.behavior_log import behavior_control
from agents.proactive import proactive_control


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
    "rag_control": rag_control,
    "graph_search": graph_search,
    "graph_backfill": graph_backfill,
    "analyze_image": analyze_image,
    "create_custom_tool": create_custom_tool,
    "patch_existing_file": patch_existing_file,
    "browser_control": browser_control,
    "get_joke": get_joke,
    "spotify_control": spotify_control,
    "send_whatsapp_message": send_whatsapp_message,
    "manage_contacts": manage_contacts,
    "reminder_control": reminder_control,
    "scheduler_control": scheduler_control,
    "get_screen_context": get_screen_context,
    "behavior_control": behavior_control,
    "proactive_control": proactive_control,
}

TOOLS_SCHEMA = [
    _schema(
        "open_application",
        "Ouvre une application installée sur l'ordinateur de l'utilisateur.",
        {
            "app_name": {
                "type": "string",
                "description": "Le nom de l'application (ex: notepad, chrome, calc)",
            }
        },
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
            "action": {
                "type": "string",
                "enum": ["list", "create_dir", "move"],
                "description": "L'action à effectuer",
            },
            "path": {"type": "string", "description": "Le chemin du fichier ou dossier à cibler"},
            "target_folder": {
                "type": "string",
                "description": "Le dossier de destination (nécessaire uniquement si action='move')",
            },
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
        ["action"],
    ),
    _schema(
        "email_control",
        "Permet de lire les derniers e-mails de la boîte de réception ou d'en envoyer un nouveau.",
        {
            "action": {
                "type": "string",
                "enum": ["list", "send"],
                "description": "'list' pour afficher les derniers messages, 'send' pour en envoyer un.",
            },
            "recipient": {
                "type": "string",
                "description": "Adresse e-mail du destinataire (requis si action='send').",
            },
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
            "action": {
                "type": "string",
                "enum": ["list", "add"],
                "description": "'list' pour voir les prochains événements, 'add' pour en créer un nouveau.",
            },
            "summary": {
                "type": "string",
                "description": "Titre du rendez-vous/événement (requis pour action='add').",
            },
            "start_time": {
                "type": "string",
                "description": "Date et heure de début au format ISO (ex: 2026-08-12T14:00:00).",
            },
            "end_time": {
                "type": "string",
                "description": "Date et heure de fin au format ISO (ex: 2026-08-12T15:00:00).",
            },
            "limit": {"type": "integer", "description": "Nombre d'événements à afficher (par défaut 5)."},
        },
        ["action"],
    ),
    _schema(
        "create_full_project",
        "Initialise un projet complet : crée le dossier dans Code, génère un dépôt GitHub et configure un Vault Obsidian.",
        {
            "project_name": {
                "type": "string",
                "description": "Le nom du projet (ex: monika-v2, api-backend, portfolio)",
            },
            "private": {
                "type": "boolean",
                "description": "True pour rendre le dépôt GitHub privé (par défaut), False pour public.",
            },
        },
        ["project_name"],
    ),
    _schema(
        "run_script",
        "Exécute une commande ou un script Bash dans le terminal local.",
        {
            "command": {
                "type": "string",
                "description": "La commande Bash exacte à exécuter (ex: 'ls -la', 'python3 script.py', 'git status').",
            },
            "workdir": {
                "type": "string",
                "description": "Le dossier d'exécution de la commande (ex: '/home/adam/Documents/Code/monika').",
            },
        },
        ["command"],
    ),
    _schema(
        "memory_control",
        "Stocke ou recherche des informations importantes à long terme (préférences de l'utilisateur, chemins de projets, règles de code, faits personnels). La recherche ('search') est sémantique : elle retrouve les souvenirs par sens, pas seulement par mot-clé exact.",
        {
            "action": {
                "type": "string",
                "enum": ["save", "search", "list"],
                "description": "'save' pour enregistrer/mettre à jour une mémoire, 'search' pour chercher par sens/mot-clé, 'list' pour tout afficher.",
            },
            "key": {
                "type": "string",
                "description": "Pour 'save' : clé d'identification (ex: 'editeur_prefere'). Pour 'search' : le texte de la requête (ex: 'éditeur de code').",
            },
            "value": {
                "type": "string",
                "description": "L'information exacte à retenir (requise si action='save').",
            },
            "category": {
                "type": "string",
                "description": "Catégorie facultative (ex: 'preferences', 'projets', 'regles').",
            },
        },
        ["action"],
    ),
    _schema(
        "rag_control",
        "RAG (Retrieval-Augmented Generation) sur les documents personnels de l'utilisateur : indexe des fichiers (PDF, Word, texte, markdown...) puis retrouve par sens les passages pertinents pour répondre à une question, avec la source exacte. Utilise cet outil dès que l'utilisateur pose une question sur le contenu d'un de ses fichiers/documents déjà indexés, ou demande d'indexer/ajouter un document à sa base de connaissances.",
        {
            "action": {
                "type": "string",
                "enum": ["ingest", "search", "list", "delete"],
                "description": "'ingest' pour indexer un fichier ou un dossier, 'search' pour interroger les documents indexés, 'list' pour voir les documents indexés, 'delete' pour en retirer un.",
            },
            "path": {
                "type": "string",
                "description": "Chemin du fichier ou dossier à indexer (requis pour action='ingest'). Formats acceptés : .txt, .md, .csv, .json, .py, .pdf, .docx.",
            },
            "query": {
                "type": "string",
                "description": "La question ou les termes de recherche (requis pour action='search').",
            },
            "doc_name": {
                "type": "string",
                "description": "Chemin exact du document à retirer de l'index, tel qu'affiché par action='list' (requis pour action='delete').",
            },
        },
        ["action"],
    ),
    _schema(
        "graph_search",
        "Interroge le graphe de connaissances (entités + relations extraites des documents indexés via rag_control) pour répondre à des questions RELATIONNELLES précises entre des éléments identifiés (ex: 'qui a recommandé quoi à qui', 'quel projet dépend de quel outil', 'où habite X'). Complète rag_search : préfère rag_control(search) pour retrouver un passage de texte par similarité, et graph_search pour une relation précise entre entités déjà connues du graphe.",
        {
            "query": {
                "type": "string",
                "description": "La question relationnelle posée en langage naturel (ex: 'qui a recommandé le restaurant à Adam ?').",
            }
        },
        ["query"],
    ),
    _schema(
        "graph_backfill",
        "Force l'extraction immédiate des entités/relations pour les documents déjà indexés via rag_control mais pas encore intégrés au graphe de connaissances (normalement fait automatiquement par petits lots à chaque graph_search, mais utile après une grosse indexation pour ne pas attendre).",
        {
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de chunks à traiter en une fois (par défaut 200).",
            }
        },
        [],
    ),
    _schema(
        "analyze_image",
        "Analyse visuellement une image locale ou une capture d'écran (extraire du texte, lire des erreurs, décrire un schéma, identifier des éléments à l'écran).",
        {
            "image_path": {
                "type": "string",
                "description": "Le chemin du fichier image à analyser (ex: '~/Images/screenshot.png').",
            },
            "prompt": {
                "type": "string",
                "description": "Consigne précise sur ce que l'agent doit observer ou chercher dans l'image (ex: 'Que dit ce message d'erreur ?').",
            },
        },
        ["image_path"],
    ),
    _schema(
        "create_custom_tool",
        "Permet d'écrire et sauvegarder un nouvel outil Python réutilisable lorsque la demande nécessite une fonctionnalité inexistante.",
        {
            "tool_name": {
                "type": "string",
                "description": "Nom de la fonction Python en snake_case (ex: 'fetch_crypto_price').",
            },
            "python_code": {
                "type": "string",
                "description": "Code Python autonome complet définissant la fonction.",
            },
            "description": {
                "type": "string",
                "description": "Explication de ce que fait la fonction et ses paramètres.",
            },
        },
        ["tool_name", "python_code", "description"],
    ),
    _schema(
        "patch_existing_file",
        "Modifie un fichier .py déjà existant DANS LE PROJET Monika à partir d'une instruction en langage "
        "naturel (contrairement à create_custom_tool qui crée un nouvel outil isolé). Sauvegarde toujours "
        "l'original, valide et TESTE le patch avant de le rendre définitif, et restaure automatiquement le "
        "fichier d'origine en cas d'échec. À utiliser avec prudence : préfère create_custom_tool quand une "
        "nouvelle fonctionnalité peut être un outil isolé plutôt qu'une modification d'un fichier existant.",
        {
            "file_path": {
                "type": "string",
                "description": "Chemin du fichier .py à modifier, à l'intérieur du projet Monika (absolu ou relatif).",
            },
            "instruction": {
                "type": "string",
                "description": "Instruction précise en langage naturel décrivant la modification à apporter.",
            },
        },
        ["file_path", "instruction"],
    ),
    _schema(
        "browser_control",
        "Contrôle un navigateur Firefox géré par Monika elle-même (lancé automatiquement au premier "
        "besoin, avec un profil persistant dédié — aucun navigateur déjà ouvert requis côté utilisateur) : "
        "lister/changer d'onglet, naviguer, lire le contenu visible d'une page, cliquer sur un élément ou "
        "remplir un champ identifié par sa description (texte visible, rôle, label, placeholder — jamais "
        "par coordonnées x/y), ou fermer le navigateur.",
        {
            "action": {
                "type": "string",
                "enum": [
                    "list_tabs",
                    "switch_tab",
                    "navigate",
                    "read_page_content",
                    "click_element",
                    "fill_field",
                    "close_browser",
                ],
                "description": "L'action à effectuer sur le navigateur.",
            },
            "url": {
                "type": "string",
                "description": "URL de destination (requis pour action='navigate').",
            },
            "tab_id": {
                "type": "integer",
                "description": "Index de l'onglet cible tel qu'affiché par action='list_tabs' (requis pour action='switch_tab').",
            },
            "description": {
                "type": "string",
                "description": "Description de l'élément ciblé : texte visible, libellé du bouton/lien, label du champ, etc. "
                "(requis pour action='click_element' et action='fill_field').",
            },
            "text": {
                "type": "string",
                "description": "Texte à saisir dans le champ ciblé (requis pour action='fill_field').",
            },
        },
        ["action"],
    ),
    _schema(
        "get_joke",
        "Raconte une blague amusante pour développeurs ou geeks.",
        {
            "language": {
                "type": "string",
                "description": "Langue de la blague ('fr', 'en', 'es', 'de'). Par défaut 'fr'.",
            },
            "category": {
                "type": "string",
                "description": "Catégorie de blague ('neutral', 'chuck', 'all'). Par défaut 'neutral'.",
            },
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
            "query": {
                "type": "string",
                "description": "Le nom du morceau, de l'artiste ou de la playlist (pour action='play').",
            },
            "volume": {
                "type": "integer",
                "description": "Le niveau de volume de 0 à 100 (pour action='volume').",
            },
        },
        ["action"],
    ),
    _schema(
        "manage_contacts",
        "Gère le carnet d'adresses : ajouter, chercher, lister ou supprimer des contacts (Nom -> Numéro).",
        {
            "action": {
                "type": "string",
                "enum": ["add", "get", "list", "delete"],
                "description": "Action à effectuer sur les contacts.",
            },
            "name": {"type": "string", "description": "Le nom du contact (ex: 'Adam', 'Maman')."},
            "phone_number": {
                "type": "string",
                "description": "Numéro au format international commençant par '+' (ex: '+33612345678').",
            },
        },
        ["action"],
    ),
    _schema(
        "send_whatsapp_message",
        "Envoie un message WhatsApp à un destinataire en utilisant soit son prénom/nom enregistrés, soit directement son numéro.",
        {
            "recipient": {
                "type": "string",
                "description": "Nom du contact dans le carnet d'adresses (ex: 'Adam', 'Maman') OU numéro au format '+33...'.",
            },
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
            "due_at": {
                "type": "string",
                "description": "Date et heure d'échéance au format ISO (ex: '2026-08-20T09:00:00'), requis pour action='add'.",
            },
            "reminder_id": {
                "type": "integer",
                "description": "Identifiant du rappel à supprimer (requis pour action='delete', voir la liste via action='list').",
            },
            "limit": {
                "type": "integer",
                "description": "Nombre de rappels à afficher pour action='list' (par défaut 10).",
            },
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
            "instruction": {
                "type": "string",
                "description": "Ce que Monika doit faire, en langage naturel (ex: 'donne la météo de Paris', 'vérifie mes derniers e-mails'). Requis pour action='add'.",
            },
            "schedule_type": {
                "type": "string",
                "enum": ["once", "daily", "interval"],
                "description": "'once' pour une seule fois (avec 'run_at'), 'daily' pour tous les jours (avec 'time_of_day'), 'interval' pour une boucle récurrente (avec 'interval_seconds'). Requis pour action='add'.",
            },
            "run_at": {
                "type": "string",
                "description": "Date et heure ISO du déclenchement unique (ex: '2026-08-20T09:00:00'), requis si schedule_type='once'.",
            },
            "time_of_day": {
                "type": "string",
                "description": "Heure quotidienne de déclenchement au format 'HH:MM' (ex: '08:00'), requis si schedule_type='daily'.",
            },
            "interval_seconds": {
                "type": "integer",
                "description": "Période de répétition en secondes (ex: 3600 pour toutes les heures), requis si schedule_type='interval'.",
            },
            "task_id": {
                "type": "integer",
                "description": "Identifiant de la tâche à annuler (requis pour action='cancel', voir action='list').",
            },
        },
        ["action"],
    ),
    _schema(
        "get_screen_context",
        "Renvoie un résumé STRUCTURÉ de ce qui est actuellement affiché à l'écran : application "
        "active, titre de fenêtre, texte exact extrait par OCR (URLs, messages d'erreur, noms de "
        "fichiers), et une estimation de l'activité en cours. Plus précis que analyze_image pour "
        "du texte exact ; utile pour comprendre le contexte de travail actuel de l'utilisateur "
        "avant d'agir ou de répondre.",
        {},
        [],
    ),
    _schema(
        "behavior_control",
        "Consulte ('show') ou vide ('reset') le journal des habitudes d'usage de Monika (outils "
        "préférés, heures d'usage, corrections répétées de l'utilisateur). Utilise ce journal pour "
        "affiner tes réponses, et propose 'reset' si l'utilisateur exprime une préoccupation de "
        "vie privée à ce sujet.",
        {
            "action": {
                "type": "string",
                "enum": ["show", "reset"],
                "description": "'show' pour afficher le résumé comportemental, 'reset' pour vider le journal.",
            }
        },
        ["action"],
    ),
    _schema(
        "proactive_control",
        "Active ou désactive le mode silencieux des interventions autonomes de Monika (celles "
        "qu'elle prend de sa propre initiative, sans qu'on le lui demande). Utilise 'silence' si "
        "l'utilisateur demande explicitement à ne plus être dérangé/interrompu spontanément (ex: "
        "'tais-toi', 'arrête de m'interrompre'), 'resume' pour réactiver, 'status' pour vérifier "
        "l'état actuel.",
        {
            "action": {
                "type": "string",
                "enum": ["silence", "resume", "status"],
                "description": "Action à effectuer sur le mode silencieux des interventions autonomes.",
            }
        },
        ["action"],
    ),
]


def _generate_schema_from_func(func, name: str, description: str) -> dict:
    """Génère un schéma JSON à partir de la signature d'une fonction (utilisé pour les outils custom, qui n'ont pas de schéma explicite)."""
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
    """Charge les outils custom de tools/custom/ dans AVAILABLE_TOOLS et ajoute leur schéma JSON à `target_schema_list`."""
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

            AVAILABLE_TOOLS[tool_name] = func

            if not any(s["function"]["name"] == tool_name for s in target_schema_list):
                doc = (func.__doc__ or f"Outil personnalisé {tool_name}").strip()
                target_schema_list.append(_generate_schema_from_func(func, tool_name, doc))
                print(f"🧩 [Outil Personnalisé Chargé] : {tool_name}")
        except Exception as e:
            print(f"⚠️ Impossible de charger l'outil personnalisé {tool_name} : {e}")


sync_custom_tools(TOOLS_SCHEMA)
