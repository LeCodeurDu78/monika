"""Boucle de conversation principale de Monika."""

import threading
from typing import Callable, Optional

from config import SYSTEM_PROMPT, EXIT_WORDS, REMINDER_CHECK_INTERVAL_SECONDS, SCHEDULER_CHECK_INTERVAL_SECONDS
from agents.orchestrator import process_user_message
from tools.utils.reminder_tools import reminder_control
from tools.system.scheduler_tools import pop_due_tasks
from tools.system.screen_watcher import _start_screen_watcher
from voice.voice_audio import record_until_silence
from voice.voice_stt import transcribe
from voice.voice_tts import speak


def _run_session(
    get_user_input: Callable[[], Optional[str]],
    on_reply: Callable[[str], None],
    on_exit: Callable[[], None] = lambda: None,
) -> None:
    """Boucle générique de session : lit l'entrée utilisateur, exécute un tour ReAct puis transmet la réponse à `on_reply`."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        while True:
            user_text = get_user_input()
            if user_text is None:
                break
            if not user_text:
                continue

            messages.append({"role": "user", "content": user_text})
            bot_reply = process_user_message(messages)
            on_reply(bot_reply)
    except KeyboardInterrupt:
        pass
    finally:
        on_exit()


def _read_text_input() -> Optional[str]:
    """Lit une ligne au clavier ; renvoie None sur EOF ou mot de sortie explicite."""
    try:
        text = input("\nVous: ")
    except EOFError:
        return None
    return None if text.strip().lower() in ("exit", "quit") else text


def _read_voice_input() -> Optional[str]:
    """Enregistre et transcrit un tour de parole ; renvoie None si un mot de sortie est prononcé."""
    audio = record_until_silence()
    if audio.size == 0:
        return ""

    text = transcribe(audio)
    if not text:
        return ""

    print(f"Vous (voix): {text}")
    return None if _is_exit(text) else text


def _start_reminder_watcher(announce: Callable[[str], None]) -> threading.Event:
    """Démarre un thread démon qui annonce les rappels à échéance toutes les REMINDER_CHECK_INTERVAL_SECONDS."""
    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(REMINDER_CHECK_INTERVAL_SECONDS):
            due_text = reminder_control("due")
            if due_text:
                announce(due_text)

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event


def _start_scheduler_watcher(on_result: Callable[[str], None]) -> threading.Event:
    """Démarre un thread démon qui exécute les tâches planifiées à échéance (toutes les SCHEDULER_CHECK_INTERVAL_SECONDS) de façon autonome : chaque..."""
    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(SCHEDULER_CHECK_INTERVAL_SECONDS):
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

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event


def _is_exit(user_text: str) -> bool:
    lowered = user_text.strip().lower()
    return any(word in lowered for word in EXIT_WORDS)


def run_monika() -> None:
    """Lance Monika en mode texte dans le terminal."""
    print("🤖 Monika Initialisée. Comment puis-je vous aider ?")
    stop_reminders = _start_reminder_watcher(lambda text: print(f"\n🔔 Monika: {text}"))
    stop_scheduler = _start_scheduler_watcher(lambda text: print(f"\n🗓️ Monika: {text}"))
    stop_screen_watch = _start_screen_watcher(lambda text: print(f"\n🖥️ [Analyse écran] {text}"))
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


def run_monika_voice() -> None:
    """Lance Monika en mode vocal (micro en entrée, voix clonée XTTS en sortie)."""
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

    stop_reminders = _start_reminder_watcher(_announce_reminder)
    stop_scheduler = _start_scheduler_watcher(_announce_scheduled_result)
    stop_screen_watch = _start_screen_watcher(lambda text: print(f"\n🖥️ [Analyse écran] {text}"))
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
