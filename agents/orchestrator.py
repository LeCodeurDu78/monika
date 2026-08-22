"""Agent superviseur de Monika."""

import json

from config import client, MODEL_NAME, SYSTEM_PROMPT
from agents.runtime import prune_context, run_react_loop
from agents.specialists import SPECIALISTS

ORCHESTRATOR_SYSTEM_PROMPT = (
    SYSTEM_PROMPT + " "
    "Tu es la superviseure d'une équipe d'agents spécialisés : "
    + "; ".join(f"'{s.name}' ({s.description})" for s in SPECIALISTS.values())
    + ". Tu ne possèdes aucun outil d'exécution toi-même : pour toute action ou recherche d'information, tu DOIS "
    "déléguer via l'outil delegate_to_agent à l'agent le plus pertinent, avec une instruction complète et "
    "autonome (l'agent délégué ne voit PAS l'historique de la conversation, inclue donc tout le contexte "
    "nécessaire : noms, dates, contenus exacts...). Tu peux déléguer plusieurs fois, y compris à des agents "
    "différents, si la demande nécessite plusieurs domaines de compétence. Une fois toutes les délégations "
    "nécessaires terminées, réponds directement et naturellement à l'utilisateur en français, de façon concise, "
    "sans jamais mentionner l'existence des agents internes ni du processus de délégation."
)

MAX_DELEGATIONS = 8


def _delegate_tool_schema() -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": "delegate_to_agent",
                "description": (
                    "Délègue une sous-tâche à un agent spécialisé qui dispose des outils nécessaires pour "
                    "l'accomplir réellement."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent": {
                            "type": "string",
                            "enum": list(SPECIALISTS.keys()),
                            "description": "\n".join(
                                f"'{s.name}' ({s.label}) : {s.description}" for s in SPECIALISTS.values()
                            ),
                        },
                        "instruction": {
                            "type": "string",
                            "description": (
                                "Instruction complète et autonome pour l'agent délégué : que doit-il faire "
                                "exactement, avec quelles informations (l'agent n'a pas accès à la conversation)."
                            ),
                        },
                    },
                    "required": ["agent", "instruction"],
                },
            },
        }
    ]


def _run_specialist(agent_name: str, instruction: str, interactive: bool) -> str:
    """Fait tourner une boucle ReAct isolée pour le spécialiste demandé et renvoie sa réponse finale."""
    specialist = SPECIALISTS.get(agent_name)
    if specialist is None:
        known = ", ".join(SPECIALISTS.keys())
        return f"⚠️ Agent inconnu : '{agent_name}'. Agents disponibles : {known}."

    sub_messages = [
        {"role": "system", "content": specialist.system_prompt},
        {"role": "user", "content": instruction},
    ]
    print(f"🧭 [Délégation → {specialist.label}] : {instruction}")
    result = run_react_loop(
        sub_messages,
        specialist.tools_schema,
        specialist.tools,
        interactive=interactive,
    )
    print(f"✅ [{specialist.label} → Superviseur] : {result}")
    return result


def process_user_message(messages: list, max_turns: int = MAX_DELEGATIONS, interactive: bool = True) -> str:
    """Boucle du superviseur : délègue aux agents spécialisés autant que nécessaire, puis renvoie la synthèse finale."""
    if not messages or messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": ORCHESTRATOR_SYSTEM_PROMPT})
    else:
        messages[0]["content"] = ORCHESTRATOR_SYSTEM_PROMPT

    tools_schema = _delegate_tool_schema()

    for _ in range(max_turns):
        messages[:] = prune_context(messages)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
        )
        response_message = response.choices[0].message

        if not response_message.tool_calls:
            bot_reply = response_message.content or "Action terminée sans message retourné."
            messages.append({"role": "assistant", "content": bot_reply})
            return bot_reply

        messages.append(response_message)
        for tool_call in response_message.tool_calls:
            func_args = json.loads(tool_call.function.arguments or "{}")
            result = _run_specialist(
                func_args.get("agent", ""),
                func_args.get("instruction", ""),
                interactive,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    fallback_msg = f"⚠️ Limite atteinte ({max_turns} délégations). Interruption de sécurité."
    messages.append({"role": "assistant", "content": fallback_msg})
    return fallback_msg
