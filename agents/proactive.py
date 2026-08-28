"""Moteur de proactivité."""

import json
import threading
from typing import Callable, Optional

from config import client, MODEL_NAME
from core.settings import settings
from tools.knowledge.memory_tools import log_proactive_action, was_recently_notified
from tools.system.behavior_tools import get_behavior_summary
from tools.vision.screen_watcher_tools import get_latest_screen_context

DECISION_SYSTEM_PROMPT = (
    "Tu es le moteur de décision autonome de Monika, une assistante IA. Tu reçois un "
    "instantané du contexte actuel de l'utilisateur (agenda, contexte d'écran, habitudes) "
    "et tu dois décider si Monika doit intervenir de sa propre initiative, MAINTENANT, sans "
    "qu'on le lui ait demandé.\n\n"
    "Sois TRÈS conservateur : la grande majorité des battements de cœur ne doivent donner "
    "lieu à AUCUNE intervention. N'interviens que si c'est concrètement utile et non "
    "intrusif (ex: échéance imminente avec contexte pertinent, erreur bloquante affichée à "
    "l'écran depuis un moment, situation qui a un vrai coût à être ignorée). Ne commente "
    "jamais simplement ce que fait l'utilisateur par curiosité, et ne répète jamais une "
    "alerte déjà donnée pour la même situation.\n\n"
    "Réponds UNIQUEMENT avec un objet JSON valide, sans texte avant/après, sans balise "
    "markdown/```, au format exact :\n"
    '{"should_act": false, "action_type": "none", "reason": "", "payload": "", '
    '"recipient": "", "subject": ""}\n\n'
    "Règles :\n"
    "1. 'should_act' : true seulement si une intervention est clairement justifiée.\n"
    "2. 'action_type' : 'voice_tts' (parler à l'utilisateur, préférer ce mode par défaut), "
    "'whatsapp_message' (message WhatsApp à un contact précis), 'email_send' (e-mail à un "
    "destinataire précis), ou 'none' si should_act est false.\n"
    "3. 'reason' : courte description factuelle de la situation détectée (sert aussi à "
    "éviter de redéclencher la même alerte).\n"
    "4. 'payload' : pour 'voice_tts'/'whatsapp_message', le texte exact à dire/envoyer ; "
    "pour 'email_send', le corps du message. Vide si should_act est false.\n"
    "5. 'recipient' : requis pour 'whatsapp_message'/'email_send' (nom de contact connu ou "
    "adresse e-mail). Si tu n'es pas certain du destinataire, choisis 'none' plutôt que de "
    "deviner.\n"
    "6. 'subject' : requis pour 'email_send' uniquement."
)

_silent_mode = settings.PROACTIVE_SILENT_MODE
_silent_lock = threading.Lock()


def set_silent_mode(enabled: bool) -> None:
    global _silent_mode
    with _silent_lock:
        _silent_mode = enabled


def is_silent_mode() -> bool:
    with _silent_lock:
        return _silent_mode


def proactive_control(action: str) -> str:
    """Active/désactive le mode silencieux des interventions autonomes, ou en donne le statut."""
    if action == "silence":
        set_silent_mode(True)
        return "🔕 Mode silencieux activé : Monika n'interviendra plus de sa propre initiative (le watcher continue de tourner en arrière-plan)."
    if action == "resume":
        set_silent_mode(False)
        return "🔔 Mode silencieux désactivé : Monika peut de nouveau intervenir de sa propre initiative."
    if action == "status":
        return "🔕 Mode silencieux actuellement activé." if is_silent_mode() else "🔔 Interventions autonomes actuellement actives."
    return "Action non reconnue pour l'outil proactive_control (utilise 'silence', 'resume' ou 'status')."


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _gather_context_snapshot() -> dict:
    """Rassemble un instantané du contexte global : agenda, écran, comportement."""
    from tools.social.calendar_tools import calendar_control

    try:
        upcoming_events = calendar_control(action="list", limit=5)
    except Exception as e:
        upcoming_events = f"Agenda indisponible : {e}"

    return {
        "upcoming_events": upcoming_events,
        "screen_context": get_latest_screen_context() or {},
        "behavior_summary": get_behavior_summary(),
    }


def _format_snapshot(snapshot: dict) -> str:
    screen = snapshot.get("screen_context") or {}
    return "\n\n".join(
        [
            f"Agenda à venir :\n{snapshot.get('upcoming_events', 'inconnu')}",
            (
                f"Contexte d'écran actuel : app='{screen.get('app', '')}', "
                f"fenêtre='{screen.get('window_title', '')}', "
                f"activité estimée='{screen.get('activity_guess', '')}'"
            ),
            f"Résumé comportemental : {snapshot.get('behavior_summary', '')}",
        ]
    )


def _dispatch_action(action_type: str, payload: str, recipient: str, subject: str, announce: Callable[[str], None]) -> Optional[str]:
    """Exécute directement l'action décidée via le registre d'outils."""
    if action_type == "voice_tts":
        announce(payload)
        return payload

    if action_type == "whatsapp_message":
        if not recipient:
            print("⚠️ [proactive] whatsapp_message sans destinataire précis : action annulée par prudence.")
            return None
        from tools.social.whatsapp_tools import send_whatsapp_message

        try:
            send_whatsapp_message(recipient=recipient, message=payload)
            return payload
        except Exception as e:
            print(f"⚠️ [proactive] Échec de l'envoi WhatsApp autonome : {e}")
            return None

    if action_type == "email_send":
        if not recipient:
            print("⚠️ [proactive] email_send sans destinataire précis : action annulée par prudence.")
            return None
        from tools.social.email_tools import email_control

        result = email_control(action="send", recipient=recipient, subject=subject or "Message de Monika", body=payload)
        if result.startswith("Erreur"):
            print(f"⚠️ [proactive] Échec de l'envoi e-mail autonome : {result}")
            return None
        return payload

    print(f"⚠️ [proactive] Type d'action inconnu ou non géré : '{action_type}'")
    return None


def evaluate_and_act(announce: Callable[[str], None]) -> Optional[str]:
    """Un battement de cœur complet : évalue le contexte, décide, agit si pertinent et non filtré."""
    snapshot = _gather_context_snapshot()

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": DECISION_SYSTEM_PROMPT},
                {"role": "user", "content": _format_snapshot(snapshot)},
            ],
        )
        raw = response.choices[0].message.content or ""
        decision = json.loads(_strip_code_fences(raw))
    except Exception as e:
        print(f"⚠️ [proactive] Échec de l'évaluation de proactivité : {e}")
        return None

    if not decision.get("should_act"):
        return None

    reason = str(decision.get("reason", "")).strip()
    action_type = str(decision.get("action_type", "none")).strip()
    payload = str(decision.get("payload", "")).strip()
    recipient = str(decision.get("recipient", "")).strip()
    subject = str(decision.get("subject", "")).strip()

    if not reason or action_type == "none" or not payload:
        return None

    if was_recently_notified(reason, settings.PROACTIVE_DEDUP_COOLDOWN_MINUTES):
        print(f"🔕 [proactive] Intervention filtrée (déjà signalée récemment) : {reason}")
        return None

    if is_silent_mode():
        print(f"🔕 [proactive] Mode silencieux actif, intervention retenue (non exécutée) : {reason}")
        return None

    result = _dispatch_action(action_type, payload, recipient, subject, announce)
    if result is not None:
        log_proactive_action(reason, action_type, payload)
    return result
