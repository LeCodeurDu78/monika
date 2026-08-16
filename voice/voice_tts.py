"""
voice_tts.py
------------
Synthèse vocale locale via XTTS v2 (Coqui TTS), avec clonage de voix à partir
d'un court échantillon audio de référence. Plus lourd que Piper (GPU
fortement recommandé), mais qualité et expressivité nettement supérieures.
"""

import re

import numpy as np
import soundfile as sf
import torch
import torchaudio

# Contournement d'un bug de mismatch de sous-librairies cuDNN présent dans
# certains builds récents de PyTorch (CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH).
# Coût quasi nul ici : cuDNN n'intervient que pour le resampling de l'audio de
# référence, pas pour la génération elle-même.
torch.backends.cudnn.enabled = False


def _load_with_soundfile(path, *args, **kwargs):
    """Remplace torchaudio.load(), qui depuis torchaudio 2.9 dépend uniquement
    de torchcodec (donc des .so FFmpeg système). Sur une rolling release comme
    Arch, ces .so précompilés se désynchronisent régulièrement de la version
    de FFmpeg installée (voir libtorchcodec_coreN.so). soundfile s'appuie sur
    libsndfile, indépendant de FFmpeg, et suffit largement pour lire un simple
    .wav de référence."""
    data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    waveform = torch.from_numpy(data.T)  # (canaux, échantillons), comme torchaudio
    return waveform, sample_rate


torchaudio.load = _load_with_soundfile

from TTS.api import TTS

from config import XTTS_MODEL_NAME, XTTS_DEVICE, XTTS_LANGUAGE, XTTS_SPEAKER_WAV
from voice.voice_audio import play_audio

_tts = None


def _get_tts() -> TTS:
    global _tts
    if _tts is None:
        if not XTTS_SPEAKER_WAV.exists():
            raise FileNotFoundError(
                f"Échantillon de voix de référence introuvable : {XTTS_SPEAKER_WAV}\n"
                f"Place un fichier .wav de 5 à 15 secondes (voix claire, peu de bruit) "
                f"à cet emplacement, ou change VOICE_XTTS_SPEAKER_WAV dans .env."
            )

        device = XTTS_DEVICE
        if device == "cuda" and not torch.cuda.is_available():
            print("CUDA indisponible, bascule de XTTS sur CPU (ce sera nettement plus lent).")
            device = "cpu"

        print(f"Chargement du modèle XTTS v2 '{XTTS_MODEL_NAME}' sur {device}...")
        _tts = TTS(XTTS_MODEL_NAME).to(device)
    return _tts


def _clean_for_speech(text: str) -> str:
    """Nettoie le texte avant synthèse. Monika (le LLM) peut répondre avec du
    markdown ou des blocs de code, qui sonneraient très mal lus à voix haute."""
    text = re.sub(r"```.*?```", " J'ai affiché du code dans le terminal. ", text, flags=re.DOTALL)
    text = re.sub(r"[*_`#]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # liens markdown -> texte du lien
    return re.sub(r"\s+", " ", text).strip()


def speak(text: str) -> None:
    """Synthétise `text` et le joue immédiatement sur les haut-parleurs par défaut."""
    cleaned = _clean_for_speech(text)
    if not cleaned:
        return

    tts = _get_tts()
    wav = tts.tts(
        text=cleaned,
        speaker_wav=str(XTTS_SPEAKER_WAV),
        language=XTTS_LANGUAGE,
    )
    if not wav:
        return

    audio = np.asarray(wav, dtype=np.float32)
    sample_rate = tts.synthesizer.output_sample_rate  # 24000 Hz pour XTTS v2
    play_audio(audio, sample_rate)
