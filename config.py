"""Configuration centrale de Monika."""

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

# --- Analyse contextuelle de l'écran (v4) --------------------------------------
SCREEN_CONTEXT_OCR_ENABLED = settings.SCREEN_CONTEXT_OCR_ENABLED
SCREEN_CONTEXT_OCR_LANG = settings.SCREEN_CONTEXT_OCR_LANG

# --- Proactivité (v4) -----------------------------------------------------------
PROACTIVE_ENABLED = settings.PROACTIVE_ENABLED
PROACTIVE_HEARTBEAT_INTERVAL_SECONDS = settings.PROACTIVE_HEARTBEAT_INTERVAL_SECONDS
PROACTIVE_DEDUP_COOLDOWN_MINUTES = settings.PROACTIVE_DEDUP_COOLDOWN_MINUTES
PROACTIVE_SILENT_MODE = settings.PROACTIVE_SILENT_MODE

# --- Apprentissage comportemental (v4) ------------------------------------------
BEHAVIOR_LOG_ENABLED = settings.BEHAVIOR_LOG_ENABLED
