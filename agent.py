"""Boucle de conversation principale de Monika."""

import threading
from typing import Callable, Optional

from config import (
    SYSTEM_PROMPT,
    EXIT_WORDS,
    REMINDER_CHECK_INTERVAL_SECONDS,
    SCHEDULER_CHECK_INTERVAL_SECONDS,
    PROACTIVE_ENABLED,
    PROACTIVE_HEARTBEAT_INTERVAL_SECONDS,
)
from agents.orchestrator import process_user_message
from agents.proactive import evaluate_and_act
from core.watcher import start_watcher
from tools.system.behavior_log import log_behavior_event, looks_like_correction
from tools.utils.reminder_tools import reminder_control
from tools.utils.scheduler_tools import pop_due_tasks
from tools.vision.screen_watcher import _start_screen_watcher
from voice.voice_audio import record_until_silence
from voice.voice_stt import transcribe
from voice.voice_tts import speak


def _run_session(
    get_user_input: Callable[[], Optional[str]],
    on_reply: Callable[[str], None],
    on_exit: Callable[[], None] = lambda: None,
) -> None:
    """Boucle générique de session."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    had_previous_reply = False

    try:
        while True:
            user_text = get_user_input()
            if user_text is None:
                break
            if not user_text:
                continue

            if had_previous_reply and looks_like_correction(user_text):
                log_behavior_event("correction", detail=user_text)

            messages.append({"role": "user", "content": user_text})
            bot_reply = process_user_message(messages)
            had_previous_reply = True
            on_reply(bot_reply)
    except KeyboardInterrupt:
        pass
    finally:
        on_exit()


def _read_text_input() -> Optional[str]:
    """Lit une ligne au clavier."""
    try:
        text = input("\nVous: ")
    except EOFError:
        return None
    return None if text.strip().lower() in ("exit", "quit") else text


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


def _start_reminder_watcher(announce: Callable[[str], None]) -> threading.Event:
    """Démarre un watcher qui annonce les rappels."""

    def _tick() -> None:
        due_text = reminder_control("due")
        if due_text:
            announce(due_text)

    return start_watcher(REMINDER_CHECK_INTERVAL_SECONDS, _tick)


def _start_scheduler_watcher(on_result: Callable[[str], None]) -> threading.Event:
    """Démarre un watcher."""

    def _tick() -> None:
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
            on_result(result)

    return start_watcher(SCHEDULER_CHECK_INTERVAL_SECONDS, _tick)


def _start_proactive_watcher(announce: Callable[[str], None]) -> threading.Event:
    """Démarre le battement de cœur du moteur de proactivité."""
    if not PROACTIVE_ENABLED:
        return threading.Event()

    def _tick() -> None:
        try:
            evaluate_and_act(announce)
        except Exception as e:
            print(f"⚠️ [proactive] Échec du battement de cœur : {e}")

    return start_watcher(PROACTIVE_HEARTBEAT_INTERVAL_SECONDS, _tick)


def _is_exit(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    return any(word in lowered for word in EXIT_WORDS)


def run_monika() -> None:
    """Lance Monika en mode texte dans le terminal."""
    print("🤖 Monika Initialisée. Comment puis-je vous aider ?")
    stop_reminders = _start_reminder_watcher(lambda text: print(f"\n🔔 Monika: {text}"))
    stop_scheduler = _start_scheduler_watcher(lambda text: print(f"\n🗓️ Monika: {text}"))
    stop_screen_watch = _start_screen_watcher()
    stop_proactive = _start_proactive_watcher(lambda text: print(f"\n💡 Monika (initiative) : {text}"))
    try:
        _run_session(
            get_user_input=_read_text_input,
            on_reply=lambda reply: print(f"\nMonika: {reply}"),
            on_exit=lambda: print("\nMonika: Au revoir !"),
        )
    finally:
        stop_reminders.set()
        stop_scheduler.set()
        stop_screen_watch.set()
        stop_proactive.set()


def run_monika_voice() -> None:
    """Lance Monika en mode vocal."""
    print("Monika (mode vocal) initialisée.")
    speak("Bonjour, je t'écoute.")

    speech_lock = threading.Lock()

    def _safe_speak(text: str) -> None:
        with speech_lock:
            speak(text)

    def _reply(text: str) -> None:
        print(f"\nMonika: {text}")
        _safe_speak(text)

    def _announce_reminder(text: str) -> None:
        print(f"\n🔔 Monika: {text}")
        _safe_speak(text)

    def _announce_scheduled_result(text: str) -> None:
        print(f"\n🗓️ Monika: {text}")
        _safe_speak(text)

    def _announce_proactive(text: str) -> None:
        print(f"\n💡 Monika (initiative) : {text}")
        _safe_speak(text)

    stop_reminders = _start_reminder_watcher(_announce_reminder)
    stop_scheduler = _start_scheduler_watcher(_announce_scheduled_result)
    stop_screen_watch = _start_screen_watcher(lambda text: print(f"\n🖥️ [Analyse écran] {text}"))
    stop_proactive = _start_proactive_watcher(_announce_proactive)
    try:
        _run_session(
            get_user_input=_read_voice_input,
            on_reply=_reply,
            on_exit=lambda: _safe_speak("Au revoir !"),
        )
    finally:
        stop_reminders.set()
        stop_scheduler.set()
        stop_screen_watch.set()
        stop_proactive.set()
