import os
import wikipedia
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path

load_dotenv()

# Client OpenAI
client = OpenAI(
    base_url=os.getenv("LLM_BASE_URL", "http://localhost:3001/v1"),
    api_key=os.getenv("OPENAI_API_KEY")
)

MODEL_NAME = "gpt-oss-120b"
VISION_MODEL_NAME = "gemini-3-flash-preview"

# Détection automatique du dossier utilisateur de Monika
APP_DIR = Path.home() / ".monika"
APP_DIR.mkdir(parents=True, exist_ok=True)

# Configuration Embeddings
LOCAL_EMBEDDING_MODEL_NAME = "BAAI/bge-m3"
LOCAL_EMBEDDING_DEVICE = os.getenv("LOCAL_EMBEDDING_DEVICE", "")

CODE_BASE_DIR = os.path.expanduser("~/Documents/Code")
OBSIDIAN_BASE_DIR = os.path.expanduser("~/Documents/Obsidian")

wikipedia.set_lang("fr")

SYSTEM_PROMPT = (
    "Tu es Monika, un assistant IA poli, concis et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
IMAP_SERVER = os.getenv("IMAP_SERVER", "imap.gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")

STT_LANGUAGE = os.getenv("VOICE_STT_LANGUAGE", "fr")
STT_MODEL_SIZE = os.getenv("VOICE_STT_MODEL", "small")
STT_DEVICE = os.getenv("VOICE_STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("VOICE_STT_COMPUTE_TYPE", "int8")

XTTS_MODEL_NAME = os.getenv("VOICE_XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2")
XTTS_DEVICE = os.getenv("VOICE_XTTS_DEVICE", "cpu")  # "cpu" par défaut pour éviter un crash sans GPU CUDA
XTTS_LANGUAGE = os.getenv("VOICE_XTTS_LANGUAGE", STT_LANGUAGE)

XTTS_SPEAKER_WAV = Path(
    os.getenv(
        "VOICE_XTTS_SPEAKER_WAV",
        str(APP_DIR / "xtts-voices" / "monika_speaker.wav"),
    )
)

SAMPLE_RATE = 16000
FRAME_MS = 30
VAD_AGGRESSIVENESS = int(os.getenv("VOICE_VAD_AGGRESSIVENESS", "2"))
SILENCE_MS = int(os.getenv("VOICE_SILENCE_MS", "900"))
MAX_RECORD_SECONDS = float(os.getenv("VOICE_MAX_RECORD_SECONDS", "20"))

EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")
REMINDER_CHECK_INTERVAL_SECONDS = 60
SCHEDULER_CHECK_INTERVAL_SECONDS = 30