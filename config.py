"""
config.py
---------
Configuration centrale de Monika : variables d'environnement, client OpenAI
(compatible LM Studio / serveur local) et configuration de Wikipédia.
"""

import os
import wikipedia
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

load_dotenv()

# Client pointant vers le serveur local (ex: LM Studio), configurable via .env
client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:3001/v1"),
    api_key=os.getenv("OPENAI_API_KEY"),
)

MODEL_NAME = "gpt-oss-120b"
VISION_MODEL_NAME = "gemini-3-flash-preview"

# --- Embeddings locaux (mémoire + RAG) ---
LOCAL_EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LOCAL_EMBEDDING_DEVICE = "cuda"

wikipedia.set_lang("fr")

SYSTEM_PROMPT = (
    "Tu es Monika, un assistant IA poli, concis et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

# --- E-mail (IMAP/SMTP) ---
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")

# --- Voix : reconnaissance (STT) ---
STT_LANGUAGE = os.getenv("VOICE_STT_LANGUAGE", "fr")
STT_MODEL_SIZE = os.getenv("VOICE_STT_MODEL", "small")
STT_DEVICE = os.getenv("VOICE_STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("VOICE_STT_COMPUTE_TYPE", "int8")

# --- Voix : synthèse (XTTS v2, clonage de voix local) ---
XTTS_MODEL_NAME = os.getenv("VOICE_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
XTTS_DEVICE = os.getenv("VOICE_XTTS_DEVICE", "cuda")  # "cuda" recommandé, sinon "cpu"
XTTS_LANGUAGE = os.getenv("VOICE_XTTS_LANGUAGE", STT_LANGUAGE)

# Échantillon audio de référence pour le clonage de voix (5-15s), à créer avant le 1er lancement
XTTS_SPEAKER_WAV = Path(
    os.getenv(
        "VOICE_XTTS_SPEAKER_WAV",
        str(Path.home() / ".local" / "share" / "xtts-voices" / "monika_speaker.wav"),
    )
)

# --- Audio / VAD (contraint par webrtcvad : 8000/16000/32000/48000 Hz, frames 10/20/30 ms) ---
SAMPLE_RATE = 16000
FRAME_MS = 30
VAD_AGGRESSIVENESS = int(os.getenv("VOICE_VAD_AGGRESSIVENESS", "2"))  # 0 (permissif) -> 3 (strict)
SILENCE_MS = int(os.getenv("VOICE_SILENCE_MS", "900"))
MAX_RECORD_SECONDS = float(os.getenv("VOICE_MAX_RECORD_SECONDS", "20"))

# Mots qui terminent la session, en plus de Ctrl+C
EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")

REMINDER_CHECK_INTERVAL_SECONDS = 60
SCHEDULER_CHECK_INTERVAL_SECONDS = 30