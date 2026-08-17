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
from pathlib import Path

# Chargement des variables d'environnement depuis le fichier .env
load_dotenv()

# Client OpenAI pointant vers le serveur local (ex: LM Studio). L'URL était
# codée en dur ; elle est maintenant configurable via .env pour changer de
# machine/port sans toucher au code.
client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:3001/v1"),
    api_key=os.getenv("OPENAI_API_KEY")
)

# Modèle utilisé pour les appels de chat
MODEL_NAME = "gpt-oss-120b"

# Modèle utilisé pour la vision
VISION_MODEL_NAME = "gemini-3-flash-preview"

# --- Embeddings locaux (mémoire + RAG) ---
LOCAL_EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LOCAL_EMBEDDING_DEVICE = "cuda"

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

# --- Langue ---
STT_LANGUAGE = os.getenv("VOICE_STT_LANGUAGE", "fr")

# --- Reconnaissance vocale ---
STT_MODEL_SIZE = os.getenv("VOICE_STT_MODEL", "small")
STT_DEVICE = os.getenv("VOICE_STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("VOICE_STT_COMPUTE_TYPE", "int8")

# --- Synthèse vocale (XTTS v2, local, clonage de voix) ---
XTTS_MODEL_NAME = os.getenv("VOICE_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
XTTS_DEVICE = os.getenv("VOICE_XTTS_DEVICE", "cuda")  # "cuda" (GPU fortement recommandé) ou "cpu"
XTTS_LANGUAGE = os.getenv("VOICE_XTTS_LANGUAGE", STT_LANGUAGE)

# Fichier audio de référence (5-15s, voix propre, peu de bruit) utilisé pour le
# clonage de voix par XTTS. Doit exister avant le premier lancement.
XTTS_SPEAKER_WAV = Path(
    os.getenv(
        "VOICE_XTTS_SPEAKER_WAV",
        str(Path.home() / ".local" / "share" / "xtts-voices" / "monika_speaker.wav"),
    )
)

# --- Audio / VAD ---
SAMPLE_RATE = 16000    # imposé par webrtcvad (8000/16000/32000/48000) et par Whisper
FRAME_MS = 30           # 10, 20 ou 30 ms - imposé par webrtcvad
VAD_AGGRESSIVENESS = int(os.getenv("VOICE_VAD_AGGRESSIVENESS", "2"))  # 0 (permissif) -> 3 (strict)
SILENCE_MS = int(os.getenv("VOICE_SILENCE_MS", "900"))     # silence pour clore le tour de parole
MAX_RECORD_SECONDS = float(os.getenv("VOICE_MAX_RECORD_SECONDS", "20"))

# Mots qui terminent la session en plus de Ctrl+C (comparaison en minuscules, sous-chaîne)
EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")

# --- Rappels ---
REMINDER_CHECK_INTERVAL_SECONDS = 60

# --- Planification de tâches (scheduler_control) ---
SCHEDULER_CHECK_INTERVAL_SECONDS = 30