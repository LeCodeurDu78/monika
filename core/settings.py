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

    LLM_TEMPERATURE: Optional[float] = 0.3
    LLM_TIMEOUT_SECONDS: float = 120
    LLM_MAX_RETRIES: int = 3
    LLM_EXTRA_BODY_JSON: Optional[str] = None
    LLM_PASS_REASONING: bool = True

    # --- Contexte de conversation ----------------------------------------------------
    TIMEZONE: str = "Europe/Paris"
    CONTEXT_MAX_TOKENS: int = 100000
    CONTEXT_MAX_MESSAGES: int = 200
    CONTEXT_KEEP_USER_TURNS: int = 5
    # Pendant une longue tâche (un seul message utilisateur), on résume les étapes anciennes
    # en gardant au moins ces derniers messages intacts.
    CONTEXT_KEEP_RECENT_MESSAGES: int = 40
    CONTEXT_PROTECT_LAST_MESSAGES: int = 20
    TOOL_RESULT_MAX_CHARS: int = 30000
    TOOL_RESULT_OLD_MAX_CHARS: int = 8000
    # Un résultat tronqué est d'abord sauvegardé sur disque : le modèle peut le relire avec read_file/grep.
    TOOL_RESULT_SPILL_TO_DISK: bool = True
    TOOL_RESULT_SPILL_RETENTION_DAYS: int = 7

    # --- run_script ------------------------------------------------------------------
    SCRIPT_TIMEOUT_SECONDS: int = 120
    SCRIPT_MAX_TIMEOUT_SECONDS: int = 900

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
    MEM0_MIN_SCORE: float = 0.4
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

    # --- RAG : recherche dans les documents personnels --------------------------------
    RAG_ENABLED: bool = True
    # Dossiers scannés (JSON dans .env, ex. RAG_ROOTS='["/home/adam"]'). Par défaut : tout le dossier personnel.
    RAG_ROOTS: list[Path] = Field(default_factory=lambda: [Path.home()])
    # Qdrant : serveur recommandé (docker compose -f utils/docker-compose.qdrant.yml up -d).
    # Le mode local (RAG_QDRANT_URL vide) est une recherche brute en mémoire : réservé à < 20 000 extraits.
    RAG_QDRANT_URL: Optional[str] = "http://localhost:6333"
    RAG_QDRANT_API_KEY: Optional[str] = None
    RAG_QDRANT_PATH: Optional[Path] = None  # mode local uniquement ; défaut : APP_DIR/rag/qdrant
    RAG_COLLECTION: str = "monika_documents"
    # Embeddings (e5 exige les préfixes « query: » / « passage: », gérés dans rag/models.py)
    RAG_EMBED_MODEL: str = "intfloat/multilingual-e5-base"
    RAG_EMBED_DIMS: int = 768
    RAG_EMBED_DEVICE: str = "cuda"
    RAG_EMBED_BATCH: int = 16
    # Reranker (cross-encoder)
    RAG_RERANK_ENABLED: bool = True
    RAG_RERANK_MODEL: str = "BAAI/bge-reranker-v2-m3"
    RAG_RERANK_DEVICE: str = "cuda"
    RAG_RERANK_MIN_SCORE: float = 0.01  # score sigmoïde 0..1 : en dessous, l'extrait est écarté (à calibrer)
    # Recherche
    RAG_CANDIDATES: int = 30  # extraits récupérés (dense + BM25 fusionnés) avant reranking
    RAG_TOP_K: int = 5
    RAG_MAX_PER_FILE: int = 2
    # Découpage (en caractères ; ~1200 car. ≈ 300-350 tokens, sous la limite de 512 d'e5)
    RAG_CHUNK_CHARS: int = 1200
    RAG_CHUNK_OVERLAP_CHARS: int = 150
    RAG_MIN_CHUNK_CHARS: int = 120
    # Exploration
    RAG_EXTENSIONS: list[str] = Field(
        default_factory=lambda: [
            ".md", ".markdown", ".txt", ".rst", ".org", ".html", ".htm", ".pdf", ".docx",
            ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".hpp", ".go", ".rs",
            ".sh", ".sql", ".yml", ".yaml", ".toml",
        ]
    )
    RAG_EXCLUDE_DIRS: list[str] = Field(
        default_factory=lambda: [
            "node_modules", "__pycache__", "venv", "site-packages", "dist", "build", "target",
            "vendor", "snap", "Trash", "lost+found", "__MACOSX",
        ]
    )
    RAG_INCLUDE_HIDDEN: bool = False  # dossiers/fichiers commençant par « . » (.ssh, .config, .mozilla...)
    RAG_SKIP_SECRETS: bool = True  # ignore les extraits qui ressemblent à des clés/mots de passe
    RAG_MAX_FILE_MB: float = 2
    RAG_MAX_BINARY_MB: float = 50  # PDF / DOCX
    RAG_MAX_PDF_PAGES: int = 1000
    RAG_SCAN_INTERVAL_SECONDS: int = 900
    RAG_SCAN_INITIAL_DELAY_SECONDS: int = 60
    RAG_FILE_PAUSE_SECONDS: float = 0.05  # petite pause entre fichiers pour ne pas saturer le GPU/CPU

    @model_validator(mode="after")
    def _resolve_dependent_defaults(self) -> "Settings":
        if self.VOICE_XTTS_LANGUAGE is None:
            self.VOICE_XTTS_LANGUAGE = self.VOICE_STT_LANGUAGE
        if self.VOICE_XTTS_SPEAKER_WAV is None:
            self.VOICE_XTTS_SPEAKER_WAV = self.APP_DIR / "monika_speaker.wav"
        return self


settings = Settings()
settings.APP_DIR.mkdir(parents=True, exist_ok=True)