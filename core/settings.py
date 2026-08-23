"""Configuration centralisée de Monika, via pydantic-settings."""

from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Dossier applicatif -----------------------------------------------------
    APP_DIR: Path = Field(default=Path.home() / ".monika")

    # --- LLM ---------------------------------------------------------------------
    MODEL_NAME: str = "qwen3.5-122b-a10b"
    VISION_MODEL_NAME: str = "gemini-3-flash-preview"
    LLM_BASE_URL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_VISION_URL: Optional[str] = None
    OPENAI_API_KEY_VISION: Optional[str] = None

    # --- Embeddings / RAG ----------------------------------------------------------
    LOCAL_EMBEDDING_MODEL_NAME: str = "BAAI/bge-m3"
    LOCAL_EMBEDDING_DEVICE: str = ""

    # --- Dossiers projets ------------------------------------------------------------
    # Auparavant non configurables (os.path.expanduser en dur) : maintenant surchargeables.
    CODE_BASE_DIR: Path = Field(default=Path.home() / "Documents" / "Code")
    OBSIDIAN_BASE_DIR: Path = Field(default=Path.home() / "Documents" / "Obsidian")

    # --- E-mail --------------------------------------------------------------------
    EMAIL_USER: Optional[str] = None
    EMAIL_PASS: Optional[str] = None
    IMAP_SERVER: str = "imap.gmail.com"
    SMTP_SERVER: str = "smtp.gmail.com"

    # --- Voix : reconnaissance (STT, faster-whisper) ---------------------------------
    VOICE_STT_LANGUAGE: str = "fr"
    VOICE_STT_MODEL: str = "small"
    VOICE_STT_DEVICE: str = "cpu"
    VOICE_STT_COMPUTE_TYPE: str = "int8"

    # --- Voix : synthèse (TTS, XTTS v2) ----------------------------------------------
    VOICE_XTTS_MODEL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    VOICE_XTTS_DEVICE: str = "cpu"
    # None -> retombe sur VOICE_STT_LANGUAGE (résolu dans le validator ci-dessous, comme avant)
    VOICE_XTTS_LANGUAGE: Optional[str] = None
    # None -> retombe sur APP_DIR / "xtts-voices" / "monika_speaker.wav" (idem)
    VOICE_XTTS_SPEAKER_WAV: Optional[Path] = None

    # --- Voix : capture audio (VAD) ------------------------------------------------
    FRAME_MS: int = 30
    SAMPLE_RATE: int = 16000
    VOICE_SILENCE_MS: int = 900
    VOICE_VAD_AGGRESSIVENESS: int = 2
    VOICE_MAX_RECORD_SECONDS: float = 20

    # --- Tâches de fond --------------------------------------------------------------
    REMINDER_CHECK_INTERVAL_SECONDS: int = 60
    SCHEDULER_CHECK_INTERVAL_SECONDS: int = 30

    # --- Analyse visuelle passive (screen watcher) ------------------------------------
    SCREEN_WATCH_ENABLED: bool = False
    SCREEN_WATCH_INTERVAL_SECONDS: int = 120
    SCREEN_WATCH_HASH_THRESHOLD: int = 5

    @model_validator(mode="after")
    def _resolve_dependent_defaults(self) -> "Settings":
        """Résout les valeurs par défaut qui dépendent d'un autre champ, exactement comme le
        faisait config.py (ex: XTTS_LANGUAGE retombait sur STT_LANGUAGE si non fourni)."""
        if self.VOICE_XTTS_LANGUAGE is None:
            self.VOICE_XTTS_LANGUAGE = self.VOICE_STT_LANGUAGE
        if self.VOICE_XTTS_SPEAKER_WAV is None:
            self.VOICE_XTTS_SPEAKER_WAV = self.APP_DIR / "xtts-voices" / "monika_speaker.wav"
        return self


settings = Settings()
settings.APP_DIR.mkdir(parents=True, exist_ok=True)