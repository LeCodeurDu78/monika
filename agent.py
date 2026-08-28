"""Boucle de conversation principale de Monika."""

import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from config import SYSTEM_PROMPT, EXIT_WORDS
from agents.orchestrator import process_user_message
from agents.proactive import evaluate_and_act
from core.native_scheduler import register_daily, unregister
from core.settings import settings
from core.wake_store import acquire as acquire_lock, drain_wake_results as drain_wake_outbox, release as release_lock
from core.watcher import start_daily_trigger, start_watcher
from tools.system.behavior_tools import log_behavior_event, looks_like_correction
from tools.system.curator import ensure_curator_scheduled
from tools.utils.briefing_tools import run_morning_briefing
from tools.utils.reminder_tools import reminder_control
from tools.utils.scheduler_tools import pop_due_tasks
from tools.vision.screen_watcher_tools import _start_screen_watcher
from voice.voice_audio import record_until_silence
from voice.voice_stt import transcribe
from voice.voice_tts import speak

_WAKE_KIND_ICONS = {"reminder": "⏰", "task": "🗓️", "briefing": "☀️"}


def _is_exit(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    return any(word in lowered for word in EXIT_WORDS)


@dataclass
class Channel:
    """Adapte la session au mode d'E/S : lecture de l'entrée + restitution des messages."""

    get_input: Callable[[], Optional[str]]
    speak_replies: bool = False
    _speech_lock: threading.Lock = field(default_factory=threading.Lock)

    def _maybe_speak(self, text: str) -> None:
        if self.speak_replies:
            with self._speech_lock:
                speak(text)

    def deliver(self, text: str, icon: Optional[str] = None) -> None:
        """Affiche (et, en mode vocal, prononce) un message de Monika."""
        prefix = f"{icon} " if icon else ""
        print(f"\n{prefix}Monika: {text}")
        self._maybe_speak(text)


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
    had_previous_reply = False

    try:
        while True:
            user_text = channel.get_input()
            if user_text is None:
                break
            if not user_text:
                continue

            if had_previous_reply and looks_like_correction(user_text):
                log_behavior_event("correction", detail=user_text)

            messages.append({"role": "user", "content": user_text})
            bot_reply = process_user_message(messages)
            had_previous_reply = True
            channel.deliver(bot_reply)
    except KeyboardInterrupt:
        pass
    finally:
        channel.deliver("Au revoir !")


def _start_background_watchers(channel: Channel) -> list[threading.Event]:
    """Démarre tous les threads de fond de Monika (rappels, tâches planifiées, veille écran, \
    proactivité, briefing du matin) et renvoie leurs événements d'arrêt."""

    def _reminder_tick() -> None:
        due_text = reminder_control("due")
        if due_text:
            channel.deliver(due_text, icon="⏰")

    def _scheduler_tick() -> None:
        for task_id, instruction in pop_due_tasks():
            print(f"🗓️ [Tâche planifiée #{task_id}] Exécution : {instruction}")
            task_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "system",
                    "content": (
                        "Contexte : l'échéance d'une tâche planifiée précédemment vient d'arriver. "
                        "Aucun utilisateur n'est présent dans cette conversation pour répondre. "
                        "Exécute l'instruction ci-dessous MAINTENANT, directement avec les outils "
                        "nécessaires pour l'accomplir (ex: send_whatsapp_message, email_control, "
                        "get_weather...). N'appelle PAS scheduler_control : la planification est déjà "
                        "faite, il s'agit maintenant de l'exécuter réellement, pas de la reporter."
                    ),
                },
                {"role": "user", "content": instruction},
            ]
            try:
                result = process_user_message(task_messages, interactive=False)
            except Exception as e:
                result = f"⚠️ Échec de la tâche planifiée #{task_id} : {e}"
            channel.deliver(result, icon="🗓️")

    def _proactive_tick() -> None:
        try:
            evaluate_and_act(lambda text: channel.deliver(text, icon="💡 (initiative)"))
        except Exception as e:
            print(f"⚠️ [proactive] Échec du battement de cœur : {e}")

    def _briefing_run() -> None:
        result = run_morning_briefing()
        if result:
            channel.deliver(f"☀️ Briefing du matin :\n{result}")

    stop_events = [start_watcher(settings.REMINDER_CHECK_INTERVAL_SECONDS, _reminder_tick),
                   start_watcher(settings.SCHEDULER_CHECK_INTERVAL_SECONDS, _scheduler_tick), _start_screen_watcher()]
    if settings.PROACTIVE_ENABLED:
        stop_events.append(start_watcher(settings.PROACTIVE_HEARTBEAT_INTERVAL_SECONDS, _proactive_tick))
    else:
        stop_events.append(threading.Event())
    if settings.MORNING_BRIEFING_ENABLED:
        stop_events.append(start_daily_trigger("morning_briefing", settings.MORNING_BRIEFING_TIME, _briefing_run))
    else:
        stop_events.append(threading.Event())

    return stop_events


def _sync_native_daily_triggers() -> None:
    """(Ré)enregistre le déclenchement natif quotidien du briefing du matin (filet de sécurité si
    Monika n'est pas lancée à l'heure prévue) : voir core/native_scheduler.py."""
    if not settings.NATIVE_SCHEDULING_ENABLED:
        return

    if settings.MORNING_BRIEFING_ENABLED:
        register_daily("morning_briefing", settings.MORNING_BRIEFING_TIME, kind="briefing")
    else:
        unregister("morning_briefing")


def _announce_pending_wake_messages(channel: Channel) -> None:
    """Annonce les résultats produits par un réveil natif survenu pendant que Monika était arrêtée."""
    for kind, message in drain_wake_outbox():
        icon = _WAKE_KIND_ICONS.get(kind, "📬")
        channel.deliver(f"(pendant mon absence) {message}", icon=icon)


def _run_monika(channel: Channel, greeting: str) -> None:
    """Lance une session Monika complète (verrou, watchers, boucle, nettoyage) pour un `Channel` donné."""
    print(greeting)
    if channel.speak_replies:
        speak("Bonjour, je t'écoute.")

    acquire_lock()
    _sync_native_daily_triggers()
    ensure_curator_scheduled()
    _announce_pending_wake_messages(channel)

    stop_events = _start_background_watchers(channel)
    try:
        _run_session(channel)
    finally:
        for stop_event in stop_events:
            stop_event.set()
        release_lock()


def run_monika() -> None:
    """Lance Monika en mode texte dans le terminal."""
    channel = Channel(get_input=_read_text_input, speak_replies=False)
    _run_monika(channel, greeting="🤖 Monika Initialisée. Comment puis-je vous aider ?")


def run_monika_voice() -> None:
    """Lance Monika en mode vocal."""
    channel = Channel(get_input=_read_voice_input, speak_replies=True)
    _run_monika(channel, greeting="Monika (mode vocal) initialisée.")