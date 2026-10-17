import os
import re
import signal
import subprocess
from pathlib import Path

from core.settings import settings

# Motifs dangereux. « dd » est cherché comme commande entière : l'ancienne sous-chaîne "dd "
# bloquait aussi des commandes anodines comme « git add . ».
_FORBIDDEN_PATTERNS = [
    (re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+(/|~|\$HOME)(\s|$|\*)"), "rm -rf sur / ou ~"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "mkfs"),
    (re.compile(r"(^|[;&|]\s*|\bsudo\s+)dd\s+"), "dd"),
    (re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"), "fork bomb"),
]
FORBIDDEN_COMMANDS = [label for _, label in _FORBIDDEN_PATTERNS]  # conservé pour compatibilité

_MAX_OUTPUT_CHARS = 20000


def _clip(text: str) -> str:
    """Garde le début et la fin d'une longue sortie (les erreurs sont souvent en fin)."""
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    half = _MAX_OUTPUT_CHARS // 2
    return f"{text[:half]}\n... [{len(text) - _MAX_OUTPUT_CHARS} caractères omis] ...\n{text[-half:]}"


def run_script(command: str, workdir: str = None, timeout: int = None) -> str:
    """Exécute une commande dans le terminal local."""
    try:
        for pattern, label in _FORBIDDEN_PATTERNS:
            if pattern.search(command):
                return f"⚠️ Action bloquée : La commande contient un modèle dangereux ('{label}')."

        target_dir = Path(workdir).expanduser() if workdir else Path.home()
        if not target_dir.exists():
            return f"Erreur : Le répertoire de travail '{target_dir}' n'existe pas."

        limit = settings.SCRIPT_TIMEOUT_SECONDS if timeout in (None, 0) else int(timeout)
        limit = max(1, min(limit, settings.SCRIPT_MAX_TIMEOUT_SECONDS))

        # Nouveau groupe de processus : au timeout on tue aussi les enfants du shell
        # (sinon un `sleep` ou un serveur lancé par la commande survit).
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=str(target_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
            partial = []
            if (stdout or "").strip():
                partial.append(f"--- STDOUT (partiel) ---\n{_clip(stdout.strip())}")
            if (stderr or "").strip():
                partial.append(f"--- STDERR (partiel) ---\n{_clip(stderr.strip())}")
            return (
                f"⚠️ Commande interrompue : temps limite de {limit} s dépassé. "
                f"Relance avec un paramètre timeout plus grand (max {settings.SCRIPT_MAX_TIMEOUT_SECONDS} s) "
                "ou lance-la en arrière-plan (nohup ... &).\n" + "\n".join(partial)
            ).strip()

        output = []
        if stdout.strip():
            output.append(f"--- STDOUT ---\n{_clip(stdout.strip())}")
        if stderr.strip():
            output.append(f"--- STDERR ---\n{_clip(stderr.strip())}")

        if not output:
            return f"Commande exécutée avec succès (Code de sortie : {proc.returncode}, aucune sortie texte)."

        return f"Code de sortie : {proc.returncode}\n" + "\n".join(output)

    except Exception as e:
        return f"Erreur lors de l'exécution du script : {str(e)}"
