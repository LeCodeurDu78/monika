"""
agent.py
---------
Boucle de conversation principale de l'agent Monika avec ReAct (Reason + Act),
mémoire persistante et Context Pruning automatique pour gérer les tokens.

Deux modes de session sont exposés :
- run_monika()       : mode texte dans le terminal (pratique pour déboguer sans micro).
- run_monika_voice() : mode vocal (micro + synthèse vocale), utilisé par main.py.

Les deux partagent la même boucle générique `_run_session`, qui ne diffère
que par la façon dont l'entrée utilisateur est recueillie et la réponse
restituée.
"""

import json
import threading
from typing import Callable, Optional

from config import client, MODEL_NAME, SYSTEM_PROMPT, EXIT_WORDS, REMINDER_CHECK_INTERVAL_SECONDS, SCHEDULER_CHECK_INTERVAL_SECONDS
from tools.registry import AVAILABLE_TOOLS, TOOLS_SCHEMA
from tools.utils.reminder_tools import reminder_control
from tools.system.scheduler_tools import pop_due_tasks
from voice.voice_audio import record_until_silence
from voice.voice_stt import transcribe
from voice.voice_tts import speak


# Limite maximale de messages dans le contexte avant pruning (élagage).
MAX_CONTEXT_MESSAGES = 18

# Longueur au-delà de laquelle un résultat d'outil est tronqué par le pruning.
TOOL_RESULT_MAX_CHARS = 1500
TOOL_RESULT_TRUNCATED_CHARS = 1200


def _prune_context(messages: list) -> list:
    """Compacte et élague l'historique des messages pour éviter d'exploser le contexte.

    1. Raccourcit les sorties d'outils trop longues (logs, gros fichiers).
    2. Conserve le prompt système et réduit les anciens échanges.
    """
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            content = str(msg.get("content", ""))
            if len(content) > TOOL_RESULT_MAX_CHARS:
                msg["content"] = (
                    content[:TOOL_RESULT_TRUNCATED_CHARS]
                    + "\n... [Résultat tronqué par Context Pruning pour économiser le contexte]"
                )

    if len(messages) <= MAX_CONTEXT_MESSAGES:
        return messages

    system_msg = messages[0]  # On conserve le SYSTEM_PROMPT
    recent_messages = messages[-(MAX_CONTEXT_MESSAGES - 1):]  # On garde les derniers échanges

    pruned = [
        system_msg,
        {
            "role": "system",
            "content": "ℹ️ [Context Pruning] Les anciens échanges de la session ont été archivés pour maintenir des performances optimales.",
        },
    ] + recent_messages

    print("✂️ [Context Pruning] L'historique de contexte a été élagué avec succès.")
    return pruned

def _execute_tool_call(tool_call, interactive: bool = True) -> str:
    """Exécute un appel d'outil demandé par le modèle et retourne son résultat en texte.

    `interactive=False` (utilisé pour les tâches planifiées exécutées en tâche
    de fond, voir `_start_scheduler_watcher`) :
    - refuse automatiquement run_script au lieu de demander une confirmation
      au clavier : un thread de fond ne doit jamais rester bloqué sur un
      `input()` pendant qu'une session interactive tourne en parallèle.
    - refuse aussi scheduler_control(action='add') : sans ce garde-fou, un
      modèle qui interprète mal l'instruction peut re-planifier la tâche au
      lieu de l'exécuter, ce qui la reporterait indéfiniment sans jamais rien
      faire. Le refus est renvoyé comme résultat d'outil, ce qui laisse au
      modèle une chance de se corriger et d'appeler le bon outil dans la
      même boucle ReAct.
    """
    func_name = tool_call.function.name
    func_args = json.loads(tool_call.function.arguments)
    func_args.pop("", None)  # certains modèles envoient une clé "" vide quand l'outil n'a pas de paramètres

    if not interactive:
         if func_name == "scheduler_control" and func_args.get("action") == "add":
            return (
                "Action refusée : impossible de planifier une nouvelle tâche depuis l'exécution "
                "d'une tâche déjà à échéance (risque de la reporter indéfiniment sans jamais l'accomplir). "
                "L'échéance est déjà arrivée : exécute l'instruction MAINTENANT avec l'outil approprié "
                "(ex: send_whatsapp_message, email_control, get_weather...), ne la re-planifie pas."
            )

    print(f"⚙️ [Action de Monika] : Exécution de {func_name}({func_args})...")
    tool_function = AVAILABLE_TOOLS[func_name]
    return str(tool_function(**func_args))


def process_user_message(messages: list, max_turns: int = 10, interactive: bool = True) -> str:
    """Envoie l'historique de conversation au modèle et exécute la boucle ReAct
    avec Context Pruning.

    `interactive=False` désactive les confirmations bloquantes (voir
    `_execute_tool_call`) ; utilisé pour l'exécution autonome des tâches
    planifiées par `_start_scheduler_watcher`.
    """
    for _ in range(max_turns):
        messages[:] = _prune_context(messages)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        # Si aucun outil n'est appelé, le modèle renvoie sa réponse finale.
        if not response_message.tool_calls:
            bot_reply = response_message.content or "Action terminée sans message retourné."
            messages.append({"role": "assistant", "content": bot_reply})
            return bot_reply

        # ReAct : exécution des outils demandés.
        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            function_result = _execute_tool_call(tool_call, interactive=interactive)
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": function_result,
            })

    fallback_msg = f"⚠️ Limite atteinte ({max_turns} étapes de actions). Interruption de sécurité."
    messages.append({"role": "assistant", "content": fallback_msg})
    return fallback_msg


def _run_session(
    get_user_input: Callable[[], Optional[str]],
    on_reply: Callable[[str], None],
    on_exit: Callable[[], None] = lambda: None,
) -> None:
    """Boucle générique de session : recueille l'entrée utilisateur, exécute le
    tour ReAct puis transmet la réponse à `on_reply`.

    `get_user_input` doit renvoyer :
    - une chaîne non vide -> traitée comme message utilisateur ;
    - une chaîne vide ("") -> rien à traiter, on redemande sans spammer le modèle ;
    - None -> fin de session (mot de sortie, EOF, saisie annulée...).

    Ctrl+C interrompt proprement la session à tout moment (lecture, appel modèle
    ou exécution d'un outil) sans remonter d'exception à l'appelant.
    """
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
        return ""  # rien entendu, on réécoute sans spammer le modèle

    text = transcribe(audio)
    if not text:
        return ""

    print(f"Vous (voix): {text}")
    return None if _is_exit(text) else text


def _start_reminder_watcher(announce: Callable[[str], None]) -> threading.Event:
    """Démarre un thread démon qui vérifie périodiquement (toutes les
    REMINDER_CHECK_INTERVAL_SECONDS) les rappels arrivés à échéance et les
    annonce via `announce`, sans que l'utilisateur ait à demander quoi que
    ce soit.

    Renvoie un `threading.Event` : l'appelant doit faire `.set()` dessus à la
    fin de la session pour arrêter proprement le thread (sinon il continue de
    tourner en arrière-plan jusqu'à la fin du processus, sans faire de mal
    grâce à `daemon=True`, mais autant le stopper proprement).
    """
    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(REMINDER_CHECK_INTERVAL_SECONDS):
            due_text = reminder_control("due")
            if due_text:
                announce(due_text)

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event


def _start_scheduler_watcher(on_result: Callable[[str], None]) -> threading.Event:
    """Démarre un thread démon qui vérifie périodiquement (toutes les
    SCHEDULER_CHECK_INTERVAL_SECONDS) les tâches planifiées arrivées à
    échéance (scheduler_control) et les exécute de façon AUTONOME : chaque
    instruction est envoyée au modèle dans une conversation isolée (jamais
    celle de l'utilisateur, pour ne pas polluer son contexte), qui peut alors
    appeler n'importe quel outil pour l'accomplir. Le résultat final est
    transmis à `on_result`.

    Exécuté avec interactive=False : une tâche planifiée qui tenterait
    d'exécuter une commande Bash est automatiquement refusée plutôt que de
    bloquer le thread sur une confirmation clavier.

    Renvoie un `threading.Event` à positionner (`.set()`) pour arrêter le
    thread proprement en fin de session, comme `_start_reminder_watcher`.
    """
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
    """Lance Monika en mode texte dans le terminal (pratique pour déboguer sans micro)."""
    print("🤖 Monika Initialisée. Comment puis-je vous aider ?")
    stop_reminders = _start_reminder_watcher(lambda text: print(f"\n🔔 Monika: {text}"))
    stop_scheduler = _start_scheduler_watcher(lambda text: print(f"\n🗓️ Monika: {text}"))
    try:
        _run_session(
            get_user_input=_read_text_input,
            on_reply=lambda reply: print(f"\nMonika: {reply}"),
            on_exit=lambda: print("\nMonika: Au revoir !"),
        )
    finally:
        stop_reminders.set()
        stop_scheduler.set()


def run_monika_voice() -> None:
    """Lance Monika en mode vocal (micro en entrée, voix clonée XTTS en sortie)."""
    print("Monika (mode vocal) initialisée.")
    speak("Bonjour, je t'écoute.")

    # Les watchers de rappels et de tâches planifiées tournent dans des threads
    # séparés et peuvent vouloir parler en même temps que la boucle principale :
    # un verrou évite que plusieurs audios se chevauchent sur les haut-parleurs.
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
    try:
        _run_session(
            get_user_input=_read_voice_input,
            on_reply=_reply,
            on_exit=lambda: _safe_speak("Au revoir !"),
        )
    finally:
        stop_reminders.set()
        stop_scheduler.set()
