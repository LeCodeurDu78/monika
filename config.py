"""Configuration centrale de Monika.

Ce module ne contient plus de logique de lecture d'environnement : toute la config est
déclarée dans `core.settings.Settings`. Ce fichier ne fait que (1) construire les objets qui
dépendent de la config (clients OpenAI, réglage wikipedia) et (2) ré-exporter les valeurs sous
les noms historiquement utilisés dans le reste du projet, pour ne rien casser en aval.

À terme, les nouveaux modules devraient importer directement `from core.settings import settings`
plutôt que ces alias — conservés ici uniquement pour la compatibilité pendant la migration.
"""

import wikipedia
from openai import OpenAI

from core.settings import settings

# --- Dossier applicatif -----------------------------------------------------
APP_DIR = settings.APP_DIR

# --- LLM ---------------------------------------------------------------------
MODEL_NAME = settings.MODEL_NAME
VISION_MODEL_NAME = settings.VISION_MODEL_NAME

client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.OPENAI_API_KEY)
client_vision = OpenAI(base_url=settings.LLM_VISION_URL, api_key=settings.OPENAI_API_KEY_VISION)

SYSTEM_PROMPT = (
    "Tu es Monika, une assistante IA polie, concise et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

# --- Embeddings / RAG ---------------------------------------------------------
LOCAL_EMBEDDING_MODEL_NAME = settings.LOCAL_EMBEDDING_MODEL_NAME
LOCAL_EMBEDDING_DEVICE = settings.LOCAL_EMBEDDING_DEVICE

# --- Dossiers projets ----------------------------------------------------------
CODE_BASE_DIR = str(settings.CODE_BASE_DIR)
OBSIDIAN_BASE_DIR = str(settings.OBSIDIAN_BASE_DIR)

# --- Recherche web -------------------------------------------------------------
wikipedia.set_lang("fr")

# --- E-mail ----------------------------------------------------------------
EMAIL_USER = settings.EMAIL_USER
EMAIL_PASS = settings.EMAIL_PASS
IMAP_SERVER = settings.IMAP_SERVER
SMTP_SERVER = settings.SMTP_SERVER

# --- Voix : reconnaissance (STT, faster-whisper) --------------------------------
STT_LANGUAGE = settings.VOICE_STT_LANGUAGE
STT_MODEL_SIZE = settings.VOICE_STT_MODEL
STT_DEVICE = settings.VOICE_STT_DEVICE
STT_COMPUTE_TYPE = settings.VOICE_STT_COMPUTE_TYPE

# --- Voix : synthèse (TTS, XTTS v2) -----------------------------------------
XTTS_MODEL_NAME = settings.VOICE_XTTS_MODEL
XTTS_DEVICE = settings.VOICE_XTTS_DEVICE
XTTS_LANGUAGE = settings.VOICE_XTTS_LANGUAGE
XTTS_SPEAKER_WAV = settings.VOICE_XTTS_SPEAKER_WAV

# --- Voix : capture audio (VAD) ---------------------------------------------
FRAME_MS = settings.FRAME_MS
SAMPLE_RATE = settings.SAMPLE_RATE
SILENCE_MS = settings.VOICE_SILENCE_MS
VAD_AGGRESSIVENESS = settings.VOICE_VAD_AGGRESSIVENESS
MAX_RECORD_SECONDS = settings.VOICE_MAX_RECORD_SECONDS

EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")

# --- Tâches de fond ----------------------------------------------------------
REMINDER_CHECK_INTERVAL_SECONDS = settings.REMINDER_CHECK_INTERVAL_SECONDS
SCHEDULER_CHECK_INTERVAL_SECONDS = settings.SCHEDULER_CHECK_INTERVAL_SECONDS

# --- Analyse visuelle passive (screen watcher) --------------------------------
SCREEN_WATCH_ENABLED = settings.SCREEN_WATCH_ENABLED
SCREEN_WATCH_INTERVAL_SECONDS = settings.SCREEN_WATCH_INTERVAL_SECONDS
SCREEN_WATCH_HASH_THRESHOLD = settings.SCREEN_WATCH_HASH_THRESHOLD
