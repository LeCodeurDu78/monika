"""Moteur ReAct générique (Reason + Act)."""

import json
import re
import time
from typing import Any, Callable, Union

from config import client, MODEL_NAME, LLM_TEMPERATURE, LLM_EXTRA_BODY
from core.settings import settings
from tools.system.fs_tools import is_inside_project

SUMMARY_PREFIX = "[Résumé de la conversation précédente"
_CHARS_PER_TOKEN = 3.5


# --- Appels au modèle --------------------------------------------------------------------------
def _llm_extra() -> dict:
    """Réglages de génération communs (température, extra_body du fournisseur)."""
    kwargs: dict[str, Any] = {}
    if LLM_TEMPERATURE is not None:
        kwargs["temperature"] = LLM_TEMPERATURE
    if LLM_EXTRA_BODY:
        kwargs["extra_body"] = LLM_EXTRA_BODY
    return kwargs


# --- Gestion du contexte -----------------------------------------------------------------------
def _estimate_tokens(messages: list) -> int:
    total = 0
    for msg in messages:
        total += len(str(msg.get("content") or ""))
        if msg.get("tool_calls"):
            total += len(json.dumps(msg["tool_calls"], ensure_ascii=False))
        total += len(str(msg.get("reasoning_content") or ""))
    return int(total / _CHARS_PER_TOKEN)


def _over_budget(messages: list) -> bool:
    return (
        len(messages) > settings.CONTEXT_MAX_MESSAGES
        or _estimate_tokens(messages) > settings.CONTEXT_MAX_TOKENS
    )


_SPILL_DIR = settings.APP_DIR / "tool_results"
_TRUNC_MARKER = "\n... [tronqué"
_SPILL_PATH_RE = re.compile(r"résultat complet : (.+?)\]")
_spill_cleaned = False


def _cleanup_spill_dir() -> None:
    """Supprime les vieux résultats sauvegardés (une fois par session)."""
    global _spill_cleaned
    if _spill_cleaned or not _SPILL_DIR.exists():
        return
    _spill_cleaned = True
    cutoff = time.time() - settings.TOOL_RESULT_SPILL_RETENTION_DAYS * 86400
    for f in _SPILL_DIR.glob("*.txt"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


def _spill(content: str, call_id: str) -> str | None:
    """Sauvegarde le résultat complet sur disque ; renvoie le chemin (None en cas d'échec)."""
    if not settings.TOOL_RESULT_SPILL_TO_DISK:
        return None
    try:
        _SPILL_DIR.mkdir(parents=True, exist_ok=True)
        _cleanup_spill_dir()
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", call_id or "") or str(int(time.time() * 1000))
        path = _SPILL_DIR / f"{int(time.time())}_{safe}.txt"
        path.write_text(content, encoding="utf-8")
        return str(path)
    except OSError:
        return None


def _cap_tool_results(messages: list, max_chars: int, protect_last: int = 0) -> None:
    """Tronque les résultats d'outils trop longs (sauf les `protect_last` derniers messages).

    Le résultat complet est d'abord sauvegardé sur disque et son chemin figure dans la note de
    troncature : la troncature n'est plus une perte, le modèle peut relire le détail avec
    read_file ou grep. Un résultat déjà tronqué garde son chemin d'origine.
    """
    limit = len(messages) - protect_last
    for index, msg in enumerate(messages):
        if index >= limit or msg.get("role") != "tool":
            continue
        content = str(msg.get("content", ""))
        marker_at = content.find(_TRUNC_MARKER)
        body_len = marker_at if marker_at != -1 else len(content)
        if body_len <= max_chars:
            continue

        if marker_at != -1:  # déjà tronqué : on reprend le chemin existant, on retire l'ancienne note
            found = _SPILL_PATH_RE.search(content[marker_at:])
            spill_path = found.group(1) if found else None
            content = content[:marker_at]
            omitted = 0  # le compte exact n'a plus de sens après une 2e troncature
        else:
            spill_path = _spill(content, msg.get("tool_call_id", ""))
            omitted = len(content) - max_chars
        msg["content"] = content[:max_chars] + _truncation_note(omitted, spill_path)


def _truncation_note(omitted: int, spill_path: str | None) -> str:
    where = f" ; résultat complet : {spill_path}" if spill_path else ""
    amount = f"{omitted} caractères omis" if omitted else "début conservé"
    return f"{_TRUNC_MARKER} : {amount}{where}]"


def _is_summary(msg: dict) -> bool:
    return msg.get("role") == "user" and str(msg.get("content", "")).startswith(SUMMARY_PREFIX)


def _render_for_summary(messages: list) -> str:
    lines = []
    for msg in messages:
        role, content = msg.get("role"), str(msg.get("content") or "")
        if role == "user":
            lines.append(f"Utilisateur : {content[:1500]}")
        elif role == "assistant":
            for call in msg.get("tool_calls") or []:
                fn = call.get("function", {})
                lines.append(f"Monika (outil) : {fn.get('name')}({str(fn.get('arguments', ''))[:150]})")
            if content:
                lines.append(f"Monika : {content[:1500]}")
        elif role == "tool":
            lines.append(f"Résultat d'outil : {content[:1200]}")
    return "\n".join(lines)


_SUMMARY_MAX_INPUT_CHARS = 200000


def _summarize(old_messages: list) -> str | None:
    """Résumé des anciens échanges par le modèle ; None en cas d'échec (on archive alors sans résumé)."""
    transcript = _render_for_summary(old_messages)
    if not transcript.strip():
        return None
    if len(transcript) > _SUMMARY_MAX_INPUT_CHARS:  # on garde la fin, la plus récente
        transcript = "[... début omis ...]\n" + transcript[-_SUMMARY_MAX_INPUT_CHARS:]
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Tu résumes une conversation entre un utilisateur et son assistante Monika, pour qu'elle puisse "
                        "la poursuivre. En français, 500 mots maximum, sans commentaire. Conserve : les demandes en cours "
                        "ou non terminées, les décisions prises, les faits utiles sur l'utilisateur, les noms, chemins, "
                        "URL, identifiants et valeurs importants, les informations clés trouvées (chiffres, conclusions, "
                        "extraits de code ou de pages utiles à la suite), les fichiers lus ou modifiés, et le résultat "
                        "(réussi ou échoué) des actions faites. "
                        "Si un ancien résumé est présent, fusionne-le."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
            **_llm_extra(),
        )
        text = (response.choices[0].message.content or "").strip()
        return text or None
    except Exception as exc:  # le résumé est un confort : ne jamais bloquer la conversation
        print(f"⚠️ [Context] Résumé impossible ({type(exc).__name__}: {exc}).")
        return None


def _compact_current_turn(messages: list) -> list:
    """Résume les étapes anciennes de la tâche EN COURS quand elle seule dépasse le budget.

    Sans cela, une longue tâche (un seul message utilisateur, des dizaines d'appels d'outils)
    ne pouvait jamais être résumée. On garde : le système, les tours précédents, la demande de
    l'utilisateur, un résumé des étapes intermédiaires, puis les derniers messages à l'identique.
    La coupe se fait toujours sur un message « assistant » pour ne séparer aucun appel d'outil
    de son résultat.
    """
    system = messages[0] if messages and messages[0].get("role") == "system" else None
    body = messages[1:] if system else list(messages)
    user_idx = [i for i, m in enumerate(body) if m.get("role") == "user" and not _is_summary(m)]
    if not user_idx:
        return messages
    request = user_idx[-1]

    cut = max(request + 1, len(body) - max(4, settings.CONTEXT_KEEP_RECENT_MESSAGES))
    while cut < len(body) and body[cut].get("role") != "assistant":
        cut += 1
    if cut >= len(body) or cut <= request + 1:
        return messages  # rien d'assez ancien à résumer

    summary = _summarize(body[request + 1 : cut])
    note = "étapes déjà effectuées dans la tâche en cours"
    if summary:
        head = {"role": "user", "content": f"{SUMMARY_PREFIX} — {note}, contexte uniquement, ce n'est pas une demande]\n{summary}"}
    else:
        head = {"role": "user", "content": f"{SUMMARY_PREFIX} — indisponible : les premières étapes de la tâche ont été archivées]"}
    print("✂️ [Context] Étapes anciennes de la tâche en cours résumées.")
    return ([system] if system else []) + body[: request + 1] + [head] + body[cut:]


def prune_context(messages: list) -> list:
    """Garde le contexte sous le budget : tronque les résultats d'outils, puis résume les anciens tours.

    Le découpage se fait toujours à une frontière de message utilisateur (ou d'étape assistant pour
    la tâche en cours), ce qui évite de séparer un appel d'outil de son résultat (l'API rejette les
    messages « tool » orphelins). Les résultats tronqués sont sauvegardés sur disque (voir _cap_tool_results).
    """
    _cap_tool_results(messages, settings.TOOL_RESULT_MAX_CHARS)
    if not _over_budget(messages):
        return messages

    # 1) Les vieux résultats d'outils ont déjà été exploités : on les réduit.
    _cap_tool_results(messages, settings.TOOL_RESULT_OLD_MAX_CHARS, protect_last=settings.CONTEXT_PROTECT_LAST_MESSAGES)
    if not _over_budget(messages):
        return messages

    # 2) Résumé des anciens tours.
    system = messages[0] if messages and messages[0].get("role") == "system" else None
    body = messages[1:] if system else list(messages)
    user_idx = [i for i, m in enumerate(body) if m.get("role") == "user" and not _is_summary(m)]
    keep = max(1, settings.CONTEXT_KEEP_USER_TURNS)
    cut = user_idx[-keep] if len(user_idx) > keep else (user_idx[-1] if len(user_idx) > 1 else 0)

    if cut > 0:
        summary = _summarize(body[:cut])
        if summary:
            head = {"role": "user", "content": f"{SUMMARY_PREFIX} — contexte uniquement, ce n'est pas une demande]\n{summary}"}
        else:
            head = {
                "role": "user",
                "content": f"{SUMMARY_PREFIX} — indisponible : les anciens échanges ont été archivés]",
            }
        body = [head] + body[cut:]
        print("✂️ [Context] Anciens échanges résumés.")

    pruned = ([system] if system else []) + body

    # 3) Une seule tâche très longue domine encore le contexte : on résume ses étapes anciennes.
    if _over_budget(pruned):
        pruned = _compact_current_turn(pruned)

    # 4) Dernier recours (les résultats complets restent lisibles sur disque).
    if _estimate_tokens(pruned) > settings.CONTEXT_MAX_TOKENS * 1.5:
        _cap_tool_results(pruned, 1500, protect_last=6)
    return pruned


# --- Exécution des outils ----------------------------------------------------------------------
def execute_tool_call(tool_call, available_tools: dict, interactive: bool = True) -> str:
    """Exécute un appel d'outil demandé par le modèle.

    Toute erreur est renvoyée au modèle sous forme de texte (et non levée), pour qu'il puisse
    corriger ses arguments ou changer d'approche au lieu d'interrompre la session.
    """
    func_name = tool_call.function.name
    try:
        func_args = json.loads(tool_call.function.arguments or "{}")
    except json.JSONDecodeError as exc:
        return f"❌ Arguments JSON invalides pour {func_name} ({exc}). Renvoie l'appel avec un JSON valide."
    if not isinstance(func_args, dict):
        return f"❌ Les arguments de {func_name} doivent être un objet JSON (clé/valeur)."
    func_args.pop("", None)

    if not interactive:
        if func_name == "scheduler_control" and func_args.get("action") == "add":
            return (
                "Action refusée : impossible de planifier une nouvelle tâche depuis l'exécution "
                "d'une tâche déjà à échéance (risque de la reporter indéfiniment sans jamais l'accomplir). "
                "L'échéance est déjà arrivée : exécute l'instruction MAINTENANT avec l'outil approprié "
                "(ex: send_whatsapp_message, email_control, get_weather...), ne la re-planifie pas."
            )
        if func_name == "patch_existing_file":
            return (
                "Action refusée : la modification du code de Monika (patch_existing_file) ne peut pas "
                "s'exécuter depuis une tâche autonome/planifiée, sans supervision directe de l'utilisateur. "
                "Demande à l'utilisateur de faire cette modification dans une conversation interactive."
            )
        if func_name in ("write_file", "edit_file") and is_inside_project(str(func_args.get("path", ""))):
            return (
                "Action refusée : une tâche autonome/planifiée ne peut pas modifier les fichiers du projet Monika "
                "elle-même, sans supervision directe de l'utilisateur. Demande-le dans une conversation interactive."
            )
        if (func_name == "user_memory" and func_args.get("action") in ("add", "delete")) or (
            func_name == "deep_memory" and func_args.get("action") == "retain"
        ):
            return (
                "Action refusée : une tâche autonome/planifiée ne peut pas modifier la mémoire (ajout ou "
                "suppression de souvenirs). Le contenu qu'elle traite (e-mails, pages web...) n'est pas "
                "supervisé et pourrait chercher à y glisser de fausses informations. La lecture reste possible."
            )

    if func_name not in available_tools:
        return f"⚠️ L'outil '{func_name}' n'existe pas. Utilise uniquement les outils de ta liste."

    print(f"⚙️ [Action] : Exécution de {func_name}({func_args})...")
    try:
        return str(available_tools[func_name](**func_args))
    except Exception as exc:
        return (
            f"❌ Erreur dans {func_name} : {type(exc).__name__}: {exc}. "
            "Vérifie les paramètres (noms, types, valeurs requises) et corrige, ou essaie une autre approche."
        )


# --- Boucle ReAct ------------------------------------------------------------------------------
def run_react_loop(
    messages: list,
    tools_schema: Union[list, Callable[[], list]],
    available_tools: dict,
    max_turns: int = 10,
    interactive: bool = True,
) -> str:
    """Envoie l'historique au modèle et exécute la boucle ReAct jusqu'à obtenir une réponse finale.

    `tools_schema` peut être une fonction : elle est rappelée à chaque étape, ce qui permet
    de voir les outils ajoutés en cours de route (create_custom_tool).
    """
    for _ in range(max_turns):
        messages[:] = prune_context(messages)

        schema = tools_schema() if callable(tools_schema) else tools_schema
        kwargs: dict[str, Any] = {"model": MODEL_NAME, "messages": messages, **_llm_extra()}
        if schema:
            kwargs["tools"] = schema
            kwargs["tool_choice"] = "auto"

        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            return f"⚠️ Erreur de communication avec le modèle : {type(exc).__name__}: {exc}"
        if not response.choices:
            return "⚠️ Le modèle n'a renvoyé aucune réponse."
        response_message = response.choices[0].message

        if not response_message.tool_calls:
            bot_reply = response_message.content or "Action terminée sans message retourné."
            messages.append({"role": "assistant", "content": bot_reply})
            return bot_reply

        assistant_msg = {
            "role": "assistant",
            "content": response_message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in response_message.tool_calls
            ],
        }
        # Modèles à raisonnement : le raisonnement doit accompagner les appels d'outils d'un même tour.
        reasoning = getattr(response_message, "reasoning_content", None)
        if reasoning and settings.LLM_PASS_REASONING:
            assistant_msg["reasoning_content"] = reasoning
        messages.append(assistant_msg)

        for tool_call in response_message.tool_calls:
            function_result = execute_tool_call(tool_call, available_tools, interactive=interactive)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": function_result,
                }
            )

    fallback_msg = f"⚠️ Limite atteinte ({max_turns} étapes d'actions). Interruption de sécurité."
    messages.append({"role": "assistant", "content": fallback_msg})
    return fallback_msg
