"""État partagé du compagnon 3D (Monika)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict

VALID_STATES = ("idle", "listening", "thinking", "speaking")


@dataclass
class AvatarState:
    state: str = "idle"
    amplitude: float = 0.0  # 0..1, utilisé pour l'ouverture de mâchoire pendant "speaking"
    text: str = ""  # dernière phrase prononcée/entendue (facultatif, affichage debug)
    updated_at: float = 0.0


_lock = threading.Lock()
_state = AvatarState(updated_at=time.time())


def set_state(state: str, amplitude: float = 0.0, text: str = "") -> None:
    """Met à jour l'état du compagnon. Thread-safe, appelable depuis n'importe quel thread."""
    if state not in VALID_STATES:
        raise ValueError(f"État inconnu : {state!r} (attendu parmi {VALID_STATES})")
    with _lock:
        _state.state = state
        _state.amplitude = max(0.0, min(1.0, amplitude))
        if text:
            _state.text = text
        _state.updated_at = time.time()


def set_amplitude(amplitude: float) -> None:
    """Met à jour uniquement l'amplitude (utilisé pendant la lecture audio pour le lipsync)."""
    with _lock:
        _state.amplitude = max(0.0, min(1.0, amplitude))
        _state.updated_at = time.time()


def snapshot() -> dict:
    """Renvoie une copie de l'état courant, prête pour la sérialisation JSON."""
    with _lock:
        return asdict(_state)
