"""
tools/system_tools.py
----------------------
Outils de contrôle du système : lancement d'applications, volume,
capture d'écran et contrôle média (spécifique Hyprland/Linux).
"""

import os
import psutil
import subprocess
from datetime import datetime


def open_application(app_name: str) -> str:
    """Ouvre une application de manière complètement détachée du terminal."""
    try:
        # Nettoyage du nom pour éviter les erreurs de saisie
        app_clean = app_name.lower().strip()

        # Lancement en arrière-plan détaché du processus Python
        subprocess.Popen(
            [app_clean],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        return f"Application '{app_name}' lancée avec succès."
    except FileNotFoundError:
        return f"Impossible de trouver l'application '{app_name}'. Vérifiez le nom binaire."
    except Exception as e:
        return f"Erreur lors du lancement de {app_name} : {str(e)}"


def system_control(action: str, value: int = 5, filename: str = None) -> str:
    """Gère le volume, la musique et les captures d'écran sous Hyprland."""
    try:
        try:
            val = int(value)
        except (TypeError, ValueError):
            val = 5

        if action == "volume_up":
            subprocess.run(["pamixer", "-i", str(val)], check=True)
            return f"Volume augmenté de {val}%."

        elif action == "volume_down":
            subprocess.run(["pamixer", "-d", str(val)], check=True)
            return f"Volume diminué de {val}%."

        elif action == "screenshot":
            images_dir = os.path.expanduser("~/Images")
            os.makedirs(images_dir, exist_ok=True)  # S'assure que le dossier existe

            # Si l'utilisateur a donné un nom, on l'utilise (en ajoutant .png si oublié)
            if filename:
                clean_name = filename.strip()
                if not clean_name.endswith(".png"):
                    clean_name += ".png"
            else:
                # Nom par défaut horodaté (ex: screenshot_20260811_230415.png)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                clean_name = f"screenshot_{timestamp}.png"

            path = os.path.join(images_dir, clean_name)
            subprocess.run(["grim", path], check=True)
            return f"Capture d'écran enregistrée sous '{clean_name}' dans {images_dir}."

        elif action == "media_toggle":
            subprocess.run(["playerctl", "play-pause"], check=True)
            return "Lecture/Pause basculée."

        return "Action système non reconnue."
    except Exception as e:
        return f"Erreur lors de l'exécution : {str(e)}"

def get_system_stats() -> str:
    """Récupère l'utilisation actuelle du CPU, de la mémoire RAM, du disque et de la batterie."""
    try:
        cpu_usage = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        stats = [
            f"• CPU : {cpu_usage}%",
            f"• RAM : {ram.percent}% utilisé ({ram.used // (1024**2)} Mo / {ram.total // (1024**2)} Mo)",
            f"• Disque (/) : {disk.percent}% utilisé ({disk.used // (1024**3)} Go / {disk.total // (1024**3)} Go)"
        ]

        # Récupération de la batterie si disponible (PC portable)
        battery = psutil.sensors_battery()
        if battery:
            plugged = "en charge" if battery.power_plugged else "sur batterie"
            stats.append(f"• Batterie : {battery.percent}% ({plugged})")

        return "Statistiques du système :\n" + "\n".join(stats)
    except Exception as e:
        return f"Erreur lors de la récupération des statistiques système : {str(e)}"