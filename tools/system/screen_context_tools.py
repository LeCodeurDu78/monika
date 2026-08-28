"""Analyse contextuelle de l'écran."""

import io
import platform
import shutil
import subprocess
from typing import Optional

from PIL import Image

from core.settings import settings

SCREEN_CONTEXT_OCR_ENABLED = settings.SCREEN_CONTEXT_OCR_ENABLED
SCREEN_CONTEXT_OCR_LANG = settings.SCREEN_CONTEXT_OCR_LANG

_OCR_WARNED = False

def capture_screen_bytes() -> Optional[bytes]:
    """Capture l'écran courant et renvoie des bytes PNG en mémoire."""
    try:
        system = platform.system()
        if system == "Windows":
            from PIL import ImageGrab

            img = ImageGrab.grab()
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        if system == "Darwin":
            result = subprocess.run(
                ["screencapture", "-x", "-t", "png", "-"], capture_output=True, check=True
            )
            return result.stdout

        # Linux : grim (Wayland, dont Hyprland). Pas de fallback X11 ici, voir get_active_window()
        # pour la détection de fenêtre qui, elle, gère X11 séparément.
        result = subprocess.run(["grim", "-"], capture_output=True, check=True)
        return result.stdout
    except Exception as e:
        print(f"⚠️ [screen_context] Échec de la capture d'écran : {e}")
        return None

def _active_window_hyprland() -> Optional[dict]:
    """Hyprland (Wayland) via `hyprctl activewindow -j`."""
    if not shutil.which("hyprctl"):
        return None
    try:
        import json

        result = subprocess.run(
            ["hyprctl", "activewindow", "-j"], capture_output=True, check=True, timeout=2
        )
        data = json.loads(result.stdout.decode("utf-8", errors="ignore"))
        app = data.get("class") or data.get("initialClass") or ""
        title = data.get("title") or data.get("initialTitle") or ""
        if not app and not title:
            return None
        return {"app": app, "window_title": title}
    except Exception:
        return None


def _active_window_x11() -> Optional[dict]:
    """X11 générique via `wmctrl` + `xdotool` (fallback si pas Hyprland/Wayland)."""
    if not shutil.which("xdotool"):
        return None
    try:
        win_id = subprocess.run(
            ["xdotool", "getactivewindow"], capture_output=True, check=True, timeout=2
        ).stdout.strip()
        if not win_id:
            return None

        title = subprocess.run(
            ["xdotool", "getwindowname", win_id], capture_output=True, check=True, timeout=2
        ).stdout.decode("utf-8", errors="ignore").strip()

        app = ""
        try:
            wm_class = subprocess.run(
                ["xdotool", "getwindowclassname", win_id],
                capture_output=True,
                check=True,
                timeout=2,
            ).stdout.decode("utf-8", errors="ignore").strip()
            app = wm_class
        except Exception:
            pass

        if not app and not title:
            return None
        return {"app": app, "window_title": title}
    except Exception:
        return None


def _active_window_windows() -> Optional[dict]:
    """Windows via `pygetwindow` (import paresseux : dépendance optionnelle)."""
    try:
        import pygetwindow as gw

        win = gw.getActiveWindow()
        if win is None:
            return None
        return {"app": "", "window_title": win.title or ""}
    except Exception:
        return None


def _active_window_macos() -> Optional[dict]:
    """macOS via `AppKit` (import paresseux : dépendance optionnelle)."""
    try:
        from AppKit import NSWorkspace

        active_app = NSWorkspace.sharedWorkspace().activeApplication()
        if not active_app:
            return None
        return {"app": active_app.get("NSApplicationName", ""), "window_title": ""}
    except Exception:
        return None


def get_active_window() -> dict:
    """Renvoie `{"app": ..., "window_title": ...}` pour la fenêtre actuellement active."""
    system = platform.system()

    if system == "Windows":
        result = _active_window_windows()
    elif system == "Darwin":
        result = _active_window_macos()
    else:
        result = _active_window_hyprland() or _active_window_x11()

    return result or {"app": "", "window_title": ""}


def ocr_text(image_bytes: bytes) -> str:
    """Extrait le texte exact visible à l'écran."""
    global _OCR_WARNED

    if not SCREEN_CONTEXT_OCR_ENABLED or not image_bytes:
        return ""

    try:
        import pytesseract
    except ImportError:
        if not _OCR_WARNED:
            print(
                "⚠️ [screen_context] 'pytesseract' n'est pas installé, l'OCR est désactivé "
                "(pip install pytesseract, + le binaire tesseract-ocr sur le système)."
            )
            _OCR_WARNED = True
        return ""

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return pytesseract.image_to_string(img, lang=SCREEN_CONTEXT_OCR_LANG).strip()
    except Exception as e:
        if not _OCR_WARNED:
            print(f"⚠️ [screen_context] Échec OCR (tesseract manquant ou langue invalide ?) : {e}")
            _OCR_WARNED = True
        return ""


def get_screen_context(image_bytes: Optional[bytes] = None, vision_description: str = "") -> dict:
    """Renvoie un résumé structuré de ce qui se passe à l'écran, plutôt qu'un paragraphe libre."""
    owns_capture = image_bytes is None
    if owns_capture:
        image_bytes = capture_screen_bytes()

    window_info = get_active_window()
    raw_text = ocr_text(image_bytes) if image_bytes else ""

    activity_guess = vision_description
    if not activity_guess and image_bytes:
        try:
            from tools.vision.vision_tools import analyze_image

            activity_guess = analyze_image(
                image_bytes,
                prompt=(
                    "En une phrase courte, décris précisément l'activité probable de "
                    "l'utilisateur à partir de cette capture d'écran (ex: 'écrit un e-mail à X', "
                    "'corrige un bug Python dans le terminal', 'regarde une vidéo')."
                ),
                mime_type="image/png",
            )
        except Exception as e:
            activity_guess = f"Erreur lors de l'estimation d'activité : {e}"

    return {
        "app": window_info.get("app", ""),
        "window_title": window_info.get("window_title", ""),
        "activity_guess": activity_guess or "",
        "raw_text": raw_text,
    }
