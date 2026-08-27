"""Moteur ReAct générique (Reason + Act)."""

import json

from config import client, MODEL_NAME
from tools.system.behavior_log import log_behavior_event

MAX_CONTEXT_MESSAGES = 50
TOOL_RESULT_MAX_CHARS = 15000
TOOL_RESULT_TRUNCATED_CHARS = 12000


def prune_context(messages: list) -> list:
    """Tronque les résultats d'outils trop longs et élague les anciens échanges pour rester sous MAX_CONTEXT_MESSAGES."""
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

    system_msgs = [m for m in messages[:1]]
    recent_messages = messages[-(MAX_CONTEXT_MESSAGES - 1):]

    pruned = system_msgs + [
        {
            "role": "system",
            "content": "ℹ️ [Context Pruning] Les anciens échanges de la session ont été archivés pour maintenir des performances optimales.",
        },
    ] + recent_messages

    print("✂️ [Context Pruning] L'historique de contexte a été élagué avec succès.")
    return pruned


def execute_tool_call(tool_call, available_tools: dict, interactive: bool = True) -> str:
    """Exécute un appel d'outil demandé par le modèle, dans la limite des outils autorisés pour cet agent."""
    func_name = tool_call.function.name
    func_args = json.loads(tool_call.function.arguments or "{}")
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

    if func_name not in available_tools:
        return (
            f"⚠️ L'outil '{func_name}' n'est pas disponible pour cet agent. "
            "Délègue plutôt cette action à l'agent spécialisé compétent."
        )

    print(f"⚙️ [Action] : Exécution de {func_name}({func_args})...")
    log_behavior_event("tool_call", tool_name=func_name)
    tool_function = available_tools[func_name]
    return str(tool_function(**func_args))


def run_react_loop(
    messages: list,
    tools_schema: list,
    available_tools: dict,
    max_turns: int = 10,
    interactive: bool = True,
) -> str:
    """Envoie l'historique au modèle et exécute la boucle ReAct (Reason + Act) jusqu'à obtenir une réponse finale."""
    for _ in range(max_turns):
        messages[:] = prune_context(messages)

        kwargs = {"model": MODEL_NAME, "messages": messages}
        if tools_schema:
            kwargs["tools"] = tools_schema
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        response_message = response.choices[0].message

        if not response_message.tool_calls:
            bot_reply = response_message.content or "Action terminée sans message retourné."
            messages.append({"role": "assistant", "content": bot_reply})
            return bot_reply

        messages.append(response_message)
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
