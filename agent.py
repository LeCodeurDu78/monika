"""
agent.py
---------
Boucle de conversation principale de l'agent Monika avec ReAct (Reason + Act),
Mémoire persistant et Context Pruning automatique pour gérer les tokens.
"""

import json

from config import client, MODEL_NAME, SYSTEM_PROMPT
from tools.schemas import TOOLS_SCHEMA
from tools.registry import AVAILABLE_TOOLS

# Limite maximale de messages dans le contexte avant pruning (élagage)
MAX_CONTEXT_MESSAGES = 18


def _prune_context(messages: list) -> list:
    """Compacte et élague l'historique des messages pour éviter d'exploser le contexte.

    1. Raccourcit les sorties d'outils trop longues (logs, gros fichiers).
    2. Conserve le prompt système et réduit les anciens échanges.
    """
    # 1. Troncature des retours d'outils trop volumineux
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "tool":
            content = str(msg.get("content", ""))
            if len(content) > 1500:
                msg["content"] = content[:1200] + "\n... [Résultat tronqué par Context Pruning pour économiser le contexte]"

    # 2. Si le nombre total de messages dépasse la limite, on compacte
    if len(messages) > MAX_CONTEXT_MESSAGES:
        system_msg = messages[0]  # On conserve le SYSTEM_PROMPT
        recent_messages = messages[-(MAX_CONTEXT_MESSAGES - 1):]  # On garde les derniers échanges

        pruned = [system_msg, {
            "role": "system",
            "content": "ℹ️ [Context Pruning] Les anciens échanges de la session ont été archivés pour maintenir des performances optimales."
        }] + recent_messages

        print("✂️ [Context Pruning] L'historique de contexte a été élagué avec succès.")
        return pruned

    return messages


def _execute_tool_call(tool_call) -> str:
    """Exécute un appel d'outil demandé par le modèle et retourne son résultat en texte."""
    func_name = tool_call.function.name
    func_args = json.loads(tool_call.function.arguments)

    # 🛑 DEMANDE DE CONFIRMATION SI L'OUTIL EST "run_script"
    if func_name == "run_script":
        cmd = func_args.get("command", "")
        wdir = func_args.get("workdir", "/home/adam")

        print(f"\n⚠️  [Sécurité Terminal] Monika veut exécuter une commande Bash :")
        print(f"    ➜ Répertoire : {wdir}")
        print(f"    ➜ Commande  : {cmd}")

        while True:
            confirm = input("    Autoriser l'exécution ? (Y/n) : ").strip().lower()
            if confirm == "y":
                break
            elif confirm == "n":
                print("❌ Exécution annulée par l'utilisateur.")
                return "L'utilisateur a refusé l'exécution de cette commande Bash."
            else:
                print("⚠️  Entrée invalide. Veuillez appuyer sur 'y' pour autoriser ou 'n' pour refuser.")

    print(f"⚙️ [Action de Monika] : Exécution de {func_name}({func_args})...")

    tool_function = AVAILABLE_TOOLS[func_name]
    return str(tool_function(**func_args))


def process_user_message(messages: list, max_turns: int = 10) -> str:
    """Envoie l'historique de conversation au modèle et exécute la boucle ReAct

    avec Context Pruning.
    """
    turn_count = 0

    while turn_count < max_turns:
        turn_count += 1

        # Application du Context Pruning avant d'appeler l'API
        messages = _prune_context(messages)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto"
        )

        response_message = response.choices[0].message

        # Si aucun outil n'est appelé, le modèle renvoie sa réponse finale
        if not response_message.tool_calls:
            bot_reply = response_message.content or "Action terminée sans message retourné."
            messages.append({"role": "assistant", "content": bot_reply})
            return bot_reply

        # ReAct: Exécution des outils
        messages.append(response_message)

        for tool_call in response_message.tool_calls:
            function_result = _execute_tool_call(tool_call)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": function_result
            })

    fallback_msg = f"⚠️ Limite atteinte ({max_turns} étapes de actions). Interruption de sécurité."
    messages.append({"role": "assistant", "content": fallback_msg})
    return fallback_msg


def run_monika():
    """Lance la boucle interactive de l'assistant Monika dans le terminal."""
    print("🤖 Monika Initialisée. Comment puis-je vous aider ?")
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    while True:
        try:
            user_input = input("\nVous: ")
        except (EOFError, KeyboardInterrupt):
            print("\n\nMonika: Au revoir !")
            break

        if user_input.lower() in ["exit", "quit"]:
            break

        messages.append({"role": "user", "content": user_input})

        bot_reply = process_user_message(messages)
        print(f"\nMonika: {bot_reply}")