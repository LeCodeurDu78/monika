"""
config.py
---------
Configuration centrale de Monika : chargement des variables d'environnement,
initialisation du client OpenAI (compatible LM Studio / serveur local) et
configuration de Wikipédia.
"""

import os
import wikipedia
from dotenv import load_dotenv
from openai import OpenAI

# Chargement des variables d'environnement depuis le fichier .env
load_dotenv()

# Client OpenAI pointant vers le serveur local (ex: LM Studio sur le port 3001)
client = OpenAI(
    base_url="http://localhost:3001/v1",
    api_key=os.getenv("OPENAI_API_KEY")
)

# Modèle utilisé pour les appels de chat
MODEL_NAME = "gpt-oss-120b"

# Configuration de Wikipédia en français
wikipedia.set_lang("fr")

# Prompt système par défaut de l'agent
SYSTEM_PROMPT = (
    "Tu es Monika, un assistant IA poli, concis et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

# Variables d'environnement liées aux e-mails (relues ici pour centraliser la config)
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")