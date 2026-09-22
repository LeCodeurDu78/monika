"""Configuration composée de Monika."""

import wikipedia
from openai import OpenAI

from core.settings import settings

# --- LLM -----------------------------------------------------------------
MODEL_NAME = settings.MODEL_NAME
VISION_MODEL_NAME = settings.VISION_MODEL_NAME

client = OpenAI(base_url=settings.LLM_BASE_URL, api_key=settings.OPENAI_API_KEY)
client_vision = OpenAI(base_url=settings.LLM_VISION_URL, api_key=settings.OPENAI_API_KEY_VISION)

SYSTEM_PROMPT = (
    "Tu es Monika, une assistante IA polie, concise et efficace. "
    "Tu as accès à l'ordinateur de l'utilisateur pour effectuer des actions requises."
)

EXIT_WORDS = ("stop", "au revoir", "quitte la session", "quitte monika")

# --- Recherche web ---------------------------------------------------------
wikipedia.set_lang("fr")
