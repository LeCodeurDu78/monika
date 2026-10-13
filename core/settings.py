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
    MODEL_NAME: str = "qwen3.8-27b"
    VISION_MODEL_NAME: str = "gemini-3.5-flash"
    LLM_BASE_URL: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    LLM_VISION_URL: Optional[str] = None
    OPENAI_API_KEY_VISION: Optional[str] = None

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
    VOICE_STT_DEVICE: str = "cuda"
    VOICE_STT_COMPUTE_TYPE: str = "int8"

    # --- Voix : synthèse (TTS, XTTS v2) ----------------------------------------------
    VOICE_XTTS_MODEL: str = "tts_models/multilingual/multi-dataset/xtts_v2"
    VOICE_XTTS_DEVICE: str = "cuda"
    VOICE_XTTS_LANGUAGE: Optional[str] = None
    VOICE_XTTS_SPEAKER_WAV: Optional[Path] = None

    # --- Voix : capture audio (VAD) ------------------------------------------------
    FRAME_MS: int = 30
    SAMPLE_RATE: int = 16000
    VOICE_SILENCE_MS: int = 900
    VOICE_VAD_AGGRESSIVENESS: int = 2
    VOICE_MAX_RECORD_SECONDS: float = 20

    # --- Tâches de fond --------------------------------------------------------------
    SCHEDULER_CHECK_INTERVAL_SECONDS: int = 30

    # --- Contrôle du navigateur -------------------------------------------
    BROWSER_HEADLESS: bool = False

    # --- Avatar 3D (compagnon animé) --------------------------------------------------
    AVATAR_ENABLED: bool = True
    AVATAR_HOST: str = "127.0.0.1"
    AVATAR_PORT: int = 4228
    AVATAR_OPEN_BROWSER: bool = True

    # --- Mémoire : capture automatique ------------------------------------------------
    MEMORY_FLUSH_EVERY_TURNS: int = 3
    MEMORY_SHUTDOWN_TIMEOUT_SECONDS: float = 30

    # --- Mémoire rapide : mem0 (faits et préférences sur l'utilisateur) -----------------
    MEM0_ENABLED: bool = True
    MEM0_USER_ID: str = "user"
    MEM0_TOP_K: int = 5
    MEM0_MIN_SCORE: float = 0.2
    MEM0_LLM_MODEL: Optional[str] = None

    # --- Mémoire rapide : mem0 (embeddings) -----------------
    MEM0_EMBEDDER_PROVIDER: str = "huggingface"
    MEM0_EMBEDDER_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    MEM0_EMBEDDER_DIMS: int = 384
    MEM0_EMBEDDER_DEVICE: str = "cuda"
    MEM0_EMBEDDER_BASE_URL: Optional[str] = None
    MEM0_EMBEDDER_API_KEY: Optional[str] = None

    # --- Mémoire longue : Hindsight (projets, décisions, échanges passés) ----------------
    HINDSIGHT_ENABLED: bool = True
    HINDSIGHT_BASE_URL: str = "http://localhost:8888"
    HINDSIGHT_API_KEY: Optional[str] = None
    HINDSIGHT_BANK_ID: str = "monika"
    HINDSIGHT_TIMEOUT: float = 30
    HINDSIGHT_REFLECT_TIMEOUT: float = 180

    @model_validator(mode="after")
    def _resolve_dependent_defaults(self) -> "Settings":
        if self.VOICE_XTTS_LANGUAGE is None:
            self.VOICE_XTTS_LANGUAGE = self.VOICE_STT_LANGUAGE
        if self.VOICE_XTTS_SPEAKER_WAV is None:
            self.VOICE_XTTS_SPEAKER_WAV = self.APP_DIR / "monika_speaker.wav"
        return self


settings = Settings()
settings.APP_DIR.mkdir(parents=True, exist_ok=True)