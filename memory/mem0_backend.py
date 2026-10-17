"""Mémoire rapide de Monika (mem0) : faits et préférences durables sur l'utilisateur.

mem0 extrait ces faits des conversations avec le LLM de Monika, les range dans un Qdrant local
(~/.monika/memory/qdrant) et les retrouve par similarité sémantique, en quelques dizaines de ms.
"""

import concurrent.futures
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from core.settings import settings
from memory.common import MemoryUnavailable, describe_error, log

MEMORY_DIR = settings.APP_DIR / "memory"

# mem0 lit ces variables d'environnement À L'IMPORT : on les pose avant tout `import mem0`.
os.environ.setdefault("MEM0_TELEMETRY", "False")  # mémoire personnelle : aucune télémétrie
os.environ.setdefault("MEM0_DIR", str(MEMORY_DIR / "mem0"))  # ~/.monika plutôt que ~/.mem0

# mem0 signale à chaque démarrage deux composants optionnels absents (spaCy : extraction d'entités en
# anglais, inutile ici ; fastembed : recherche par mots-clés, voir MEMORY.md). Ce bruit n'a pas sa place
# dans le terminal de Monika ; les vraies erreurs (niveau ERROR) restent affichées.
logging.getLogger("mem0.utils.spacy_models").setLevel(logging.ERROR)
logging.getLogger("mem0.vector_stores.qdrant").setLevel(logging.ERROR)

# Consigne ajoutée au prompt d'extraction de mem0. Sans elle, mem0 retient aussi ce que dit
# l'assistant (météo, résultats de recherche...) et rédige ses souvenirs en anglais.
EXTRACTION_INSTRUCTIONS = (
    "Tu alimentes la mémoire personnelle d'un assistant. Ne retiens QUE des informations durables "
    "que l'UTILISATEUR donne sur lui-même : identité, proches, lieux de vie, travail ou études, "
    "goûts, habitudes, préférences (ton, format de réponse...), contraintes, projets personnels. "
    "N'extrais RIEN des réponses de l'assistant ni des résultats d'outils (météo, recherche web, "
    "e-mails, fichiers, prix...), ni des commandes ponctuelles (volume, ouvrir une application, "
    "lancer une musique...). Si le message ne contient aucune information durable sur l'utilisateur, "
    "n'extrais rien. Rédige chaque souvenir en français, à la troisième personne "
    "(« L'utilisateur ... »), de façon courte et autonome."
)


# --- suivi du téléchargement du modèle d'embedding ---------------------------------------------
# Le modèle est chargé dans un thread de fond : les barres de progression de Hugging Face s'y perdent
# (et gêneraient le prompt « Vous: »). On surveille donc le cache et on affiche de courtes lignes.
DOWNLOAD_POLL_SECONDS = 3.0
DOWNLOAD_STALL_SECONDS = 30.0
_UNUSED_DIRS = ("onnx/", "openvino/")
_UNUSED_FILES = {"pytorch_model.bin", "tf_model.h5", "rust_model.ot", "flax_model.msgpack"}


def _expected_download_bytes(repo_id: str) -> Optional[int]:
    """Taille attendue du téléchargement (poids + tokenizer), ou None si le Hub ne répond pas."""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(repo_id, files_metadata=True, timeout=10)
    except Exception:
        return None
    files = {s.rfilename: (s.size or 0) for s in (info.siblings or [])}
    has_safetensors = any(name.endswith(".safetensors") for name in files)
    total = 0
    for name, size in files.items():
        if name.startswith(_UNUSED_DIRS) or (has_safetensors and name in _UNUSED_FILES):
            continue  # sentence-transformers ne télécharge ni les formats ONNX/OpenVINO ni les doublons
        total += size
    return total or None


def _repo_cache_bytes(repo_id: str) -> int:
    """Octets déjà présents dans le cache Hugging Face pour ce modèle (fichiers .incomplete compris)."""
    from huggingface_hub import constants

    blobs = Path(constants.HF_HUB_CACHE) / ("models--" + repo_id.replace("/", "--")) / "blobs"
    total = 0
    try:
        for path in blobs.iterdir():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    except OSError:
        return 0
    return total


def _watch_model_download(repo_id: str, stop: threading.Event) -> None:
    """Affiche la progression du téléchargement de `repo_id` tant que `stop` n'est pas levé.

    Silencieux si le modèle est déjà en cache. Signale aussi un téléchargement qui ne progresse plus.
    """
    expected = _expected_download_bytes(repo_id)
    start = _repo_cache_bytes(repo_id)
    if expected and start >= expected:
        return  # déjà en cache : rien à montrer

    mb = 1024 * 1024
    last, last_time, last_growth = start, time.monotonic(), time.monotonic()
    begun = False
    while not stop.wait(DOWNLOAD_POLL_SECONDS):
        now, clock = _repo_cache_bytes(repo_id), time.monotonic()
        if now > last:
            speed = (now - last) / max(clock - last_time, 0.001) / mb
            if expected:
                percent = min(100, int(now * 100 / expected))
                log(
                    f"⬇️ [Mémoire] Modèle d'embedding : {now / mb:.0f}/{expected / mb:.0f} Mo "
                    f"({percent} %) — {speed:.1f} Mo/s"
                )
            else:
                log(f"⬇️ [Mémoire] Modèle d'embedding : {now / mb:.0f} Mo — {speed:.1f} Mo/s")
            begun, last_growth = True, clock
        elif begun and clock - last_growth >= DOWNLOAD_STALL_SECONDS:
            log(
                f"⏸️ [Mémoire] Le téléchargement du modèle ne progresse plus depuis "
                f"{int(clock - last_growth)} s ({now / mb:.0f} Mo reçus)."
            )
            last_growth = clock  # prochain rappel dans DOWNLOAD_STALL_SECONDS
        last, last_time = now, clock

    if begun:
        log("✅ [Mémoire] Modèle d'embedding téléchargé.")


def _embedder_config() -> dict[str, Any]:
    """Configuration de l'embedder mem0 selon le fournisseur choisi (voir MEM0_EMBEDDER_* dans settings)."""
    provider = settings.MEM0_EMBEDDER_PROVIDER.strip().lower()
    base_url = settings.MEM0_EMBEDDER_BASE_URL
    config: dict[str, Any] = {
        "model": settings.MEM0_EMBEDDER_MODEL,
        "embedding_dims": settings.MEM0_EMBEDDER_DIMS,
    }

    if provider == "huggingface":
        if base_url:  # serveur TEI compatible OpenAI
            config["huggingface_base_url"] = base_url
        else:  # modèle local (sentence-transformers) : CPU par défaut pour ne pas disputer le GPU à la voix
            config["model_kwargs"] = {"device": settings.MEM0_EMBEDDER_DEVICE}
    elif provider == "openai":  # tout endpoint /v1/embeddings compatible OpenAI
        config["openai_base_url"] = base_url or settings.LLM_BASE_URL
        config["api_key"] = settings.MEM0_EMBEDDER_API_KEY or settings.OPENAI_API_KEY
    elif provider == "ollama":
        config["ollama_base_url"] = base_url

    return {"provider": provider, "config": {k: v for k, v in config.items() if v is not None}}


def build_config() -> dict[str, Any]:
    """Configuration complète de mem0 : LLM de Monika, embedder multilingue, Qdrant local persistant."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    llm_config: dict[str, Any] = {
        "model": settings.MEM0_LLM_MODEL or settings.MODEL_NAME,
        "temperature": 0.1,
        "max_tokens": 4096,  # marge pour les modèles qui « réfléchissent » avant de répondre
        "api_key": settings.OPENAI_API_KEY,
        "openai_base_url": settings.LLM_BASE_URL,
    }

    return {
        "llm": {
            "provider": "openai",  # endpoint compatible OpenAI, comme le LLM principal de Monika
            "config": {k: v for k, v in llm_config.items() if v is not None},
        },
        "embedder": _embedder_config(),
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": "monika_user_facts",
                "path": str(MEMORY_DIR / "qdrant"),
                # mem0 ne le déduit pas de l'embedder : doit correspondre à MEM0_EMBEDDER_DIMS.
                "embedding_model_dims": settings.MEM0_EMBEDDER_DIMS,
            },
        },
        "history_db_path": str(MEMORY_DIR / "mem0_history.db"),
        "custom_instructions": EXTRACTION_INSTRUCTIONS,
    }


def _results(response: Any) -> list[dict]:
    """Extrait la liste de résultats d'une réponse mem0 ({'results': [...]} ou liste directe)."""
    if isinstance(response, dict):
        response = response.get("results", [])
    return list(response or [])


class Mem0Memory:
    """Enveloppe thread-safe autour de `mem0.Memory`.

    - L'initialisation (chargement du modèle d'embedding, ouverture de Qdrant) se fait en arrière-plan.
    - Les lectures ne sont jamais bloquées par une écriture en cours (une écriture appelle le LLM :
      plusieurs secondes) ; seules les écritures sont sérialisées entre elles.
    """

    def __init__(self) -> None:
        self._memory: Any = None
        self._error: Optional[str] = None
        self._ready = threading.Event()
        self._started = False
        self._start_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reads = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="mem0-read")

    # --- cycle de vie ----------------------------------------------------------------
    def start(self) -> None:
        """Lance l'initialisation en arrière-plan (sans effet si déjà lancée)."""
        with self._start_lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._init, daemon=True, name="mem0-init").start()

    def _init(self) -> None:
        # Un modèle d'embedding local (huggingface sans serveur) se télécharge au premier lancement : on le montre.
        stop_watch = threading.Event()
        if settings.MEM0_EMBEDDER_PROVIDER.strip().lower() == "huggingface" and not settings.MEM0_EMBEDDER_BASE_URL:
            threading.Thread(
                target=_watch_model_download,
                args=(settings.MEM0_EMBEDDER_MODEL, stop_watch),
                daemon=True,
                name="mem0-download-watch",
            ).start()
        try:
            from mem0 import Memory  # import tardif : mem0ai est une dépendance optionnelle

            memory = Memory.from_config(build_config())
            # Échauffement : force l'initialisation des composants chargés à la demande, et révèle tout de
            # suite une incohérence de dimensions plutôt qu'au premier message de l'utilisateur.
            memory.search("démarrage", top_k=1, filters={"user_id": settings.MEM0_USER_ID})
            total = len(_results(memory.get_all(filters={"user_id": settings.MEM0_USER_ID}, top_k=10_000)))
            self._memory = memory
            log(f"🧠 [Mémoire] mem0 prêt ({total} souvenir(s) sur l'utilisateur).")
        except Exception as exc:
            self._error = describe_error(exc)
            if "dimension" in str(exc).lower():
                self._error += (
                    " — si tu as changé de modèle d'embedding, supprime "
                    f"{MEMORY_DIR / 'qdrant'} (les souvenirs mem0 seront réextraits au fil des conversations)."
                )
            log(f"⚠️ [Mémoire] mem0 indisponible : {self._error}")
        finally:
            stop_watch.set()
            self._ready.set()

    def _require(self, wait: float) -> Any:
        """Renvoie l'instance mem0, en attendant au plus `wait` secondes qu'elle soit prête."""
        self.start()
        if not self._ready.wait(wait):
            raise MemoryUnavailable(
                "mem0 s'initialise encore (au premier lancement : téléchargement du modèle d'embedding)."
            )
        if self._memory is None:
            raise MemoryUnavailable(f"mem0 indisponible : {self._error}")
        return self._memory

    # --- opérations --------------------------------------------------------------------
    def search(
        self,
        query: str,
        limit: Optional[int] = None,
        wait: float = 0.0,
        timeout: Optional[float] = None,
    ) -> list[dict]:
        """Souvenirs les plus proches de `query` : [{'id', 'memory', 'score', ...}], du plus pertinent au moins."""
        memory = self._require(wait)
        future = self._reads.submit(
            memory.search,
            query,
            top_k=limit or settings.MEM0_TOP_K,
            threshold=settings.MEM0_MIN_SCORE,
            filters={"user_id": settings.MEM0_USER_ID},
        )
        try:
            return _results(future.result(timeout=timeout))
        except concurrent.futures.TimeoutError:
            raise MemoryUnavailable("la recherche mem0 a dépassé le délai imparti.") from None

    def list_all(self, limit: int = 50, wait: float = 0.0) -> list[dict]:
        """Tous les souvenirs connus (au plus `limit`)."""
        memory = self._require(wait)
        return _results(memory.get_all(filters={"user_id": settings.MEM0_USER_ID}, top_k=limit))

    def add(self, messages: Any, wait: float = 0.0) -> list[dict]:
        """Confie une conversation (ou un texte) à mem0, qui en extrait les faits à retenir.

        Renvoie les souvenirs créés ou mis à jour : [{'id', 'memory', 'event'}].
        """
        memory = self._require(wait)
        with self._write_lock:
            response = memory.add(messages, user_id=settings.MEM0_USER_ID)
        return _results(response)

    def delete(self, memory_id: str, wait: float = 0.0) -> None:
        memory = self._require(wait)
        with self._write_lock:
            memory.delete(memory_id)