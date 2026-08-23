"""Reconnaissance vocale locale via faster-whisper (CTranslate2)."""

import numpy as np
from faster_whisper import WhisperModel
from config import STT_MODEL_SIZE, STT_DEVICE, STT_COMPUTE_TYPE, STT_LANGUAGE

_model = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"Chargement du modèle Whisper '{STT_MODEL_SIZE}' " f"({STT_DEVICE}/{STT_COMPUTE_TYPE})...")
        _model = WhisperModel(STT_MODEL_SIZE, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE)
    return _model


def transcribe(audio_float32: np.ndarray, sample_rate: int = 16000) -> str:
    """Transcrit un tableau numpy float32 [-1, 1] mono en texte."""
    if audio_float32.size == 0:
        return ""
    if sample_rate != 16000:
        raise ValueError(
            f"transcribe() attend du 16000 Hz, reçu {sample_rate} Hz. "
            "Rééchantillonne avant d'appeler cette fonction."
        )

    model = _get_model()
    segments, _info = model.transcribe(
        audio_float32,
        language=STT_LANGUAGE,
        vad_filter=True,
        beam_size=5,
    )
    return " ".join(segment.text.strip() for segment in segments).strip()
