"""
tools/system/terminal_tools.py
-------------------------------
Exécution de commandes Bash locales pour Monika.
"""

import os
import subprocess

# Commandes strictement interdites pour éviter des accidents destructeurs
FORBIDDEN_COMMANDS = ["rm -rf /", "mkfs", "dd ", ":(){ :|:& };:"]


def run_script(command: str, workdir: str = "/home/adam") -> str:
    """Exécute une commande Bash sur le système, avec un garde-fou sur les
    commandes destructrices et un timeout de sécurité (30s).

    Args:
        command: La commande Bash à exécuter.
        workdir: Le répertoire de travail (par défaut /home/adam).
    """
    try:
        for forbidden in FORBIDDEN_COMMANDS:
            if forbidden in command:
                return f"⚠️ Action bloquée : La commande contient un modèle dangereux ('{forbidden}')."

        workdir = os.path.expanduser(workdir)
        if not os.path.exists(workdir):
            return f"Erreur : Le répertoire de travail '{workdir}' n'existe pas."

        result = subprocess.run(
            command,
            shell=True,
            cwd=workdir,
            capture_output=True,
            text=True,
            timeout=30
        )

        output = []
        if result.stdout.strip():
            output.append(f"--- STDOUT ---\n{result.stdout.strip()}")
        if result.stderr.strip():
            output.append(f"--- STDERR ---\n{result.stderr.strip()}")

        if not output:
            return f"Commande exécutée avec succès (Code de sortie : {result.returncode}, aucune sortie texte)."

        return f"Code de sortie : {result.returncode}\n" + "\n".join(output)

    except subprocess.TimeoutExpired:
        return "⚠️ Erreur : L'exécution du script a dépassé le temps limite autorisé (30 secondes)."
    except Exception as e:
        return f"Erreur lors de l'exécution du script : {str(e)}"