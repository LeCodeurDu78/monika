import os
import subprocess
from pathlib import Path

FORBIDDEN_COMMANDS = ["rm -rf /", "mkfs", "dd ", ":(){ :|:& };:"]


def run_script(command: str, workdir: str = None) -> str:
    """Exécute une commande dans le terminal local."""
    try:
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden in command:
                return f"⚠️ Action bloquée : La commande contient un modèle dangereux ('{forbidden}')."

        target_dir = Path(workdir).expanduser() if workdir else Path.home()

        if not target_dir.exists():
            return f"Erreur : Le répertoire de travail '{target_dir}' n'existe pas."

        result = subprocess.run(
            command, shell=True, cwd=str(target_dir), capture_output=True, text=True, timeout=30
        )

        output = []
        if result.stdout.strip():
            output.append(f"--- STDOUT ---\n{result.stdout.strip()}")
        if result.stderr.strip():
            output.append(f"--- STDERR ---\n{result.stderr.strip()}")

        if not output:
            return (
                f"Commande exécutée avec succès (Code de sortie : {result.returncode}, aucune sortie texte)."
            )

        return f"Code de sortie : {result.returncode}\n" + "\n".join(output)

    except subprocess.TimeoutExpired:
        return "⚠️ Erreur : L'exécution du script a dépassé le temps limite autorisé (30 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution du script : {str(e)}"
