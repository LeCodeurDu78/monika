"""Gestion et organisation des fichiers locaux (listage, création de dossier, déplacement)."""

import os


def manage_files(action: str, path: str, target_folder: str = "") -> str:
    """Gère et organise les fichiers locaux."""
    try:
        path = os.path.expanduser(path)

        if action == "list":
            files = os.listdir(path)
            return f"Contenu de '{path}' : {', '.join(files[:20])}"

        elif action == "create_dir":
            os.makedirs(path, exist_ok=True)
            return f"Dossier '{path}' créé avec succès."

        elif action == "move" and target_folder:
            target_folder = os.path.expanduser(target_folder)
            os.makedirs(target_folder, exist_ok=True)
            file_name = os.path.basename(path)
            destination = os.path.join(target_folder, file_name)
            os.rename(path, destination)
            return f"Fichier déplacé de '{path}' vers '{destination}'."

        return "Action non reconnue ou paramètres manquants."
    except Exception as e:
        return f"Erreur gestion de fichiers : {str(e)}"
