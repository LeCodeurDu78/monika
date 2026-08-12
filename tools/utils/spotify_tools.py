"""
tools/spotify_tools.py
----------------------
Contrôle Spotify robuste : Fallback automatique playerctl si compte non-Premium.
"""

import subprocess


def _run_playerctl(args: list) -> tuple[bool, str]:
    """Exécute une commande playerctl pour contrôler Spotify localement."""
    try:
        cmd = ["playerctl", "-p", "spotify"] + args
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, res.stdout.strip()
    except Exception as e:
        return False, str(e)


def spotify_control(action: str, query: str = "", volume: int = 50) -> str:
    """Contrôle la lecture de musique Spotify (compatible Spotify Premium et Gratuit via playerctl).

    Args:
        action: 'play', 'pause', 'next', 'previous', 'rewind', 'current', 'volume'
        query: Nom de chanson ou recherche (pour action='play')
        volume: Niveau de volume 0-100 (pour action='volume')
    """
    # 1. Action Pause
    if action == "pause":
        success, _ = _run_playerctl(["pause"])
        if success:
            return "⏸️ Musique mise en pause (via playerctl)."
        return "❌ Impossible de mettre en pause : vérifiez que Spotify est ouvert sur votre PC."

    # 2. Action Play
    elif action == "play":
        success, _ = _run_playerctl(["play"])
        if success:
            return "▶️ Lecture Spotify lancée."
        return "❌ Impossible de relancer la lecture."

    # 3. Action Rewind (Remettre la piste au début 0s)
    elif action == "rewind":
        # Tentative via position 0
        ok_pos, _ = _run_playerctl(["position", "0"])

        # Si position 0 n'est pas géré par le lecteur, on envoie 'previous' (qui remet au début du morceau)
        if not ok_pos:
            _run_playerctl(["previous"])

        _run_playerctl(["play"])
        return "⏮️ Morceau remis au début !"

    # 4. Action Suivant / Précédent
    elif action == "next":
        _run_playerctl(["next"])
        return "⏭️ Morceau suivant."

    elif action == "previous":
        _run_playerctl(["previous"])
        return "⏮️ Morceau précédent."

    # 5. Morceau en cours
    elif action == "current":
        ok_art, artist = _run_playerctl(["metadata", "artist"])
        ok_title, title = _run_playerctl(["metadata", "title"])
        if ok_art and ok_title:
            return f"🎵 En cours : '{title}' par {artist}"
        return "Aucune musique active sur Spotify."

    # 6. Réglage Volume
    elif action == "volume":
        vol_float = max(0.0, min(1.0, volume / 100.0))
        ok, _ = _run_playerctl(["volume", str(vol_float)])
        if ok:
            return f"🔊 Volume réglé à {volume}%."
        return "❌ Impossible de régler le volume."

    return f"Action '{action}' non reconnue."