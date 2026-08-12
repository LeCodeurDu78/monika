"""
tools/schemas.py
------------------
Schémas des outils (function calling) fournis au modèle OpenAI.
Séparés de la logique métier pour ne toucher qu'à un seul endroit
lors de l'ajout ou de la modification d'un outil.
"""
from tools.registry import sync_custom_tools

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Ouvre une application installée sur l'ordinateur de l'utilisateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Le nom de l'application (ex: notepad, chrome, calc)"}
                },
                "required": ["app_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtient la météo actuelle pour une ville donnée.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Le nom de la ville (ex: Paris, Lyon, Montreal)"}
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_files",
            "description": "Liste, crée des dossiers ou déplace des fichiers sur l'ordinateur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["list", "create_dir", "move"],
                               "description": "L'action à effectuer"},
                    "path": {"type": "string", "description": "Le chemin du fichier ou dossier à cibler"},
                    "target_folder": {"type": "string",
                                      "description": "Le dossier de destination (nécessaire uniquement si action='move')"}
                },
                "required": ["action", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "system_control",
            "description": "Contrôle les fonctionnalités du système Linux (volume, média, capture d'écran).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["volume_up", "volume_down", "screenshot", "media_toggle"],
                        "description": "L'action système à exécuter."
                    },
                    "value": {
                        "type": "integer",
                        "description": "La quantité ou le pourcentage exact pour le volume (ex: 5, 10, 20)."
                    }
                },
                "required": ["action", "value"]  # <-- 'value' est désormais OBLIGATOIRE !
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_control",
            "description": "Permet de lire les derniers e-mails de la boîte de réception ou d'en envoyer un nouveau.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "send"],
                        "description": "'list' pour afficher les derniers messages, 'send' pour en envoyer un."
                    },
                    "recipient": {
                        "type": "string",
                        "description": "Adresse e-mail du destinataire (requis si action='send')."
                    },
                    "subject": {
                        "type": "string",
                        "description": "Sujet de l'e-mail (requis si action='send')."
                    },
                    "body": {
                        "type": "string",
                        "description": "Contenu/Corps de l'e-mail (requis si action='send')."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Nombre de derniers e-mails à lire (par défaut 5)."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Effectue des recherches en ligne sur Wikipédia ou sur le Web pour trouver des informations récentes ou de la culture générale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["wikipedia", "duckduckgo"],
                        "description": "Utilisez 'wikipedia' pour de la culture générale ou des définitions, et 'duckduckgo' pour de l'actualité ou des recherches Web générales."
                    },
                    "query": {
                        "type": "string",
                        "description": "Les termes de la recherche."
                    }
                },
                "required": ["source", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Obtient les métriques d'utilisation en temps réel du système (CPU, RAM, Disque, Batterie).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_control",
            "description": "Consulte la liste des événements ou ajoute un rendez-vous dans Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "add"],
                        "description": "'list' pour voir les prochains événements, 'add' pour en créer un nouveau."
                    },
                    "summary": {
                        "type": "string",
                        "description": "Titre du rendez-vous/événement (requis pour action='add')."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Date et heure de début au format ISO (ex: 2026-08-12T14:00:00)."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Date et heure de fin au format ISO (ex: 2026-08-12T15:00:00)."
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Nombre d'événements à afficher (par défaut 5)."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_full_project",
            "description": "Initialise un projet complet : crée le dossier dans Code, génère un dépôt GitHub et configure un Vault Obsidian.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {
                        "type": "string",
                        "description": "Le nom du projet (ex: monika-v2, api-backend, portfolio)"
                    },
                    "private": {
                        "type": "boolean",
                        "description": "True pour rendre le dépôt GitHub privé (par défaut), False pour public."
                    }
                },
                "required": ["project_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "Exécute une commande ou un script Bash dans le terminal local.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "La commande Bash exacte à exécuter (ex: 'ls -la', 'python3 script.py', 'git status')."
                    },
                    "workdir": {
                        "type": "string",
                        "description": "Le dossier d'exécution de la commande (ex: '/home/adam/Documents/Code/monika')."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "memory_control",
            "description": "Stocke ou recherche des informations importantes à long terme (préférences de l'utilisateur, chemins de projets, règles de code, faits personnels).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["save", "search", "list"],
                        "description": "'save' pour enregistrer/mettre à jour une mémoire, 'search' pour chercher par mot-clé, 'list' pour tout afficher."
                    },
                    "key": {
                        "type": "string",
                        "description": "Clé d'identification de l'information (ex: 'editeur_prefere', 'repertoire_code', 'regle_git')."
                    },
                    "value": {
                        "type": "string",
                        "description": "L'information exacte à retenir (requise si action='save')."
                    },
                    "category": {
                        "type": "string",
                        "description": "Catégorie facultative (ex: 'preferences', 'projets', 'regles')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": "Analyse visuellement une image locale ou une capture d'écran (extraire du texte, lire des erreurs, décrire un schéma, identifier des éléments à l'écran).",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_path": {
                        "type": "string",
                        "description": "Le chemin du fichier image à analyser (ex: '/home/adam/Images/screenshot.png')."
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Consigne précise sur ce que l'agent doit observer ou chercher dans l'image (ex: 'Que dit ce message d'erreur ?')."
                    }
                },
                "required": ["image_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_custom_tool",
            "description": "Permet d'écrire et sauvegarder un nouvel outil Python réutilisable lorsque la demande nécessite une fonctionnalité inexistante.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Nom de la fonction Python en snake_case (ex: 'fetch_crypto_price')."
                    },
                    "python_code": {
                        "type": "string",
                        "description": "Code Python autonome complet définissant la fonction."
                    },
                    "description": {
                        "type": "string",
                        "description": "Explication de ce que fait la fonction et ses paramètres."
                    }
                },
                "required": ["tool_name", "python_code", "description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_joke",
            "description": "Raconte une blague amusante pour développeurs ou geeks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Langue de la blague ('fr', 'en', 'es', 'de'). Par défaut 'fr'."
                    },
                    "category": {
                        "type": "string",
                        "description": "Catégorie de blague ('neutral', 'chuck', 'all'). Par défaut 'neutral'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "spotify_control",
            "description": "Permet de contrôler Spotify : lire de la musique, mettre en pause, passer un morceau, changer le volume ou chercher des playlists.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["play", "pause", "next", "previous", "rewind", "current", "volume"],
                        "description": "L'action Spotify à exécuter."
                    },
                    "query": {
                        "type": "string",
                        "description": "Le nom du morceau, de l'artiste ou de la playlist (pour action='play' ou 'search_playlist')."
                    },
                    "volume": {
                        "type": "integer",
                        "description": "Le niveau de volume de 0 à 100 (pour action='volume')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "manage_contacts",
            "description": "Gère le carnet d'adresses : ajouter, chercher, lister ou supprimer des contacts (Nom -> Numéro).",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["add", "get", "list", "delete"],
                        "description": "Action à effectuer sur les contacts."
                    },
                    "name": {
                        "type": "string",
                        "description": "Le nom du contact (ex: 'Adam', 'Maman')."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "Numéro au format international commençant par '+' (ex: '+33612345678')."
                    }
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Envoie un message WhatsApp à un destinataire en utilisant soit son prénom/nom enregistrés, soit directement son numéro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recipient": {
                        "type": "string",
                        "description": "Nom du contact dans le carnet d'adresses (ex: 'Adam', 'Maman') OU numéro au format '+33...'."
                    },
                    "message": {
                        "type": "string",
                        "description": "Le texte du message à envoyer."
                    }
                },
                "required": ["recipient", "message"]
            }
        }
    }
]

sync_custom_tools(TOOLS_SCHEMA)