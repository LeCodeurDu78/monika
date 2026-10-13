"""Boucle de conversation principale de Monika."""

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from avatar import state as avatar_state
from avatar.server import start_avatar_server
from config import SYSTEM_PROMPT, EXIT_WORDS
from agents.orchestrator import SCHEDULED_TASK_CONTEXT, process_user_message
from core.settings import settings
from core.watcher import start_watcher
from memory.manager import memory_manager
from tools.utils.scheduler_tools import pop_due_tasks
from voice.voice_audio import record_until_silence
from voice.voice_stt import transcribe
from voice.voice_tts import speak

_EXIT_PHRASES = tuple(word for word in EXIT_WORDS if " " in word)
_EXIT_PHRASE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase) for phrase in _EXIT_PHRASES) + r")\b"
) if _EXIT_PHRASES else None


def _is_exit(user_text: str) -> bool:
    """Vrai si l'utilisateur demande explicitement la fin de session.

    Un mot isolé comme « stop » doit constituer tout le message : le chercher en
    sous-chaîne faisait quitter Monika sur « stoppe la musique ». Les formules
    multi-mots (« au revoir », « quitte monika ») restent reconnues au fil d'une phrase,
    mais uniquement sur des limites de mots.
    """
    normalized = user_text.strip().lower().strip(" .!?…,;:")
    if normalized in EXIT_WORDS:
        return True
    return bool(_EXIT_PHRASE_PATTERN and _EXIT_PHRASE_PATTERN.search(normalized))


@dataclass
class Channel:
    """Adapte la session au mode d'E/S : lecture de l'entrée + restitution des messages."""

    get_input: Callable[[], Optional[str]]
    speak_replies: bool = False
    # True pour les canaux qui n'ont pas déjà leur propre mécanisme de mise à jour de
    # l'avatar 3D : la voix pilote déjà idle/listening/thinking/speaking au fil de
    # l'audio réel (voir voice_audio.py et avatar/lipsync.py) et n'en a pas besoin ici ;
    # le texte, lui, n'a rien d'autre pour faire vivre le compagnon.
    drives_avatar: bool = False
    _speech_lock: threading.Lock = field(default_factory=threading.Lock)

    def _maybe_speak(self, text: str) -> None:
        if self.speak_replies:
            with self._speech_lock:
                speak(text)

    def deliver(self, text: str, icon: Optional[str] = None) -> None:
        """Affiche (et, en mode vocal, prononce) un message de Monika."""
        prefix = f"{icon} " if icon else ""
        print(f"\n{prefix}Monika: {text}")
        if self.drives_avatar:
            avatar_state.set_state("speaking", text=text)
        self._maybe_speak(text)
        if self.drives_avatar:
            if not self.speak_replies:
                # Sans audio pour occuper le temps, "speaking" ne durerait que le temps
                # d'un print() — bien trop court pour que le polling front-end (100 ms,
                # voir POLL_INTERVAL_MS dans script.js) ait la moindre chance de le voir.
                # On le maintient un temps proportionnel à la longueur du texte, borné
                # pour ne pas devenir pénible sur une réponse très longue.
                time.sleep(max(0.6, min(4.0, len(text) / 18)))
            avatar_state.set_state("idle")


def _read_text_input() -> Optional[str]:
    """Lit une ligne au clavier."""
    try:
        text = input("\nVous: ")
    except EOFError:
        return None
    return None if _is_exit(text) else text


def _read_voice_input() -> Optional[str]:
    """Enregistre et transcrit un tour de parole."""
    audio = record_until_silence()
    if audio.size == 0:
        return ""

    text = transcribe(audio)
    if not text:
        return ""

    print(f"Vous (voix): {text}")
    return None if _is_exit(text) else text


def _run_session(channel: Channel) -> None:
    """Boucle générique de session : lit l'entrée, traite le message, restitue la réponse."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        while True:
            if channel.drives_avatar:
                avatar_state.set_state("listening")
            user_text = channel.get_input()
            if user_text is None:
                break
            if not user_text:
                continue

            if channel.drives_avatar:
                avatar_state.set_state("thinking")
            messages.append({"role": "user", "content": user_text})
            bot_reply = process_user_message(messages)
            channel.deliver(bot_reply)
    except KeyboardInterrupt:
        pass
    finally:
        channel.deliver("Au revoir !")


def _start_background_watchers(channel: Channel) -> list[threading.Event]:
    """Démarre le thread de fond de Monika (tâches planifiées) et renvoie ses événements d'arrêt."""

    def _scheduler_tick() -> None:
        for task_id, instruction in pop_due_tasks():
            print(f"🗓️ [Tâche planifiée #{task_id}] Exécution : {instruction}")
            task_messages = [{"role": "user", "content": instruction}]
            try:
                result = process_user_message(
                    task_messages, interactive=False, context=SCHEDULED_TASK_CONTEXT
                )
            except Exception as e:
                result = f"⚠️ Échec de la tâche planifiée #{task_id} : {e}"
            channel.deliver(result, icon="🗓️")

    return [start_watcher(settings.SCHEDULER_CHECK_INTERVAL_SECONDS, _scheduler_tick)]


def _run_monika(channel: Channel, greeting: str) -> None:
    """Lance une session Monika complète (watchers, boucle, nettoyage) pour un `Channel` donné."""
    print(greeting)
    # Les mémoires s'initialisent en arrière-plan (chargement du modèle d'embedding, connexion à Hindsight)
    # pendant que l'avatar et la voix démarrent : elles sont prêtes bien avant le premier message.
    memory_manager.start()
    start_avatar_server()
    if channel.speak_replies:
        speak("Bonjour, je t'écoute.")

    stop_events = _start_background_watchers(channel)
    try:
        _run_session(channel)
    finally:
        for stop_event in stop_events:
            stop_event.set()
        memory_manager.shutdown()  # envoie les derniers échanges aux mémoires avant de quitter


def run_monika() -> None:
    """Lance Monika en mode texte dans le terminal."""
    channel = Channel(get_input=_read_text_input, speak_replies=False, drives_avatar=True)
    _run_monika(channel, greeting="🤖 Monika Initialisée. Comment puis-je vous aider ?")


def run_monika_voice() -> None:
    """Lance Monika en mode vocal."""
    channel = Channel(get_input=_read_voice_input, speak_replies=True, drives_avatar=False)
    _run_monika(channel, greeting="Monika (mode vocal) initialisée.")