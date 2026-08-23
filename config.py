"""Configuration centrale de Monika."""

import os
from pathlib import Path

import wikipedia
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


def _env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, default))


# --- Dossier applicatif -----------------------------------------------------
APP_DIR = Path(_env("APP_DIR", str(Path.home() / ".monika"))).expanduser()
APP_DIR.mkdir(parents=True, exist_ok=True)

# --- LLM ---------------------------------------------------------------------
MODEL_NAME = "qwen3.5-122b-a10b"
VISION_MODEL_NAME = "gemini-3-flash-preview"

client = OpenAI(base_url=_env("LLM_BASE_URL"), api_key=_env("OPENAI_API_KEY"))
client_vision = OpenAI(base_url=_env("LLM_VISION_URL"), api_key=_env("OPENAI_API_KEY_VISION"))

SYSTEM_PROMPT = (
    "Tu es Monika, une assistante IA polie, concise et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

# --- Embeddings / RAG ---------------------------------------------------------
LOCAL_EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LOCAL_EMBEDDING_DEVICE = _env("LOCAL_EMBEDDING_DEVICE", "")

# --- Dossiers projets ----------------------------------------------------------
CODE_BASE_DIR = os.path.expanduser("~/Documents/Code")
OBSIDIAN_BASE_DIR = os.path.expanduser("~/Documents/Obsidian")

# --- Recherche web -------------------------------------------------------------
wikipedia.set_lang("fr")

# --- E-mail ----------------------------------------------------------------
EMAIL_USER = _env("EMAIL_USER")
EMAIL_PASS = _env("EMAIL_PASS")
IMAP_SERVER = _env("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = _env("SMTP_SERVER", "smtp.gmail.com")

# --- Voix : reconnaissance (STT, faster-whisper) --------------------------------
STT_LANGUAGE = _env("VOICE_STT_LANGUAGE", "fr")
STT_MODEL_SIZE = _env("VOICE_STT_MODEL", "small")
STT_DEVICE = _env("VOICE_STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = _env("VOICE_STT_COMPUTE_TYPE", "int8")

# --- Voix : synthèse (TTS, XTTS v2) -----------------------------------------
XTTS_MODEL_NAME = _env("VOICE_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
XTTS_DEVICE = _env("VOICE_XTTS_DEVICE", "cpu")
XTTS_LANGUAGE = _env("VOICE_XTTS_LANGUAGE", STT_LANGUAGE)
XTTS_SPEAKER_WAV = Path(_env("VOICE_XTTS_SPEAKER_WAV", str(APP_DIR / "xtts-voices" / "monika_speaker.wav")))

# --- Voix : capture audio (VAD) ---------------------------------------------
FRAME_MS = 30
SAMPLE_RATE = 16000
SILENCE_MS = _env_int("VOICE_SILENCE_MS", 900)
VAD_AGGRESSIVENESS = _env_int("VOICE_VAD_AGGRESSIVENESS", 2)
MAX_RECORD_SECONDS = _env_float("VOICE_MAX_RECORD_SECONDS", 20)

EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")

# --- Tâches de fond ----------------------------------------------------------
REMINDER_CHECK_INTERVAL_SECONDS = 60
SCHEDULER_CHECK_INTERVAL_SECONDS = 30

# --- Analyse visuelle passive (screen watcher) --------------------------------
# Désactivée par défaut : l'écran peut contenir des informations sensibles, l'activation
# doit être un choix explicite de l'utilisateur via la variable d'environnement.
SCREEN_WATCH_ENABLED = _env("SCREEN_WATCH_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")
SCREEN_WATCH_INTERVAL_SECONDS = _env_int("SCREEN_WATCH_INTERVAL_SECONDS", 120)
# Distance de Hamming minimale entre deux hashs perceptifs (sur 64 bits) pour considérer que
# l'écran a "significativement changé" et justifier un appel au modèle vision.
SCREEN_WATCH_HASH_THRESHOLD = _env_int("SCREEN_WATCH_HASH_THRESHOLD", 5)