"""
agent.py
---------
Boucle de conversation principale de l'agent Monika : dialogue avec le
modèle, détection des appels d'outils, exécution locale et synthèse
de la réponse finale.
"""

import json

from config import client, MODEL_NAME, SYSTEM_PROMPT
from tools.schemas import TOOLS_SCHEMA
from tools.registry import AVAILABLE_TOOLS


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

        # Boucle tant que l'utilisateur n'entre pas strictement 'Y' ou 'n'
        while True:
            confirm = input("    Autoriser l'exécution ? (Y/n) : ").strip().lower()
            if confirm == "y":
                break  # On sort de la boucle et on continue l'exécution
            elif confirm == "n":
                print("❌ Exécution annulée par l'utilisateur.")
                return "L'utilisateur a refusé l'exécution de cette commande Bash."
            else:
                print("⚠️  Entrée invalide. Veuillez appuyer uniquement sur 'y' pour autoriser ou 'n' pour refuser.")

    print(f"⚙️ [Action de Monika] : Exécution de {func_name}({func_args})...")

    tool_function = AVAILABLE_TOOLS[func_name]
    return str(tool_function(**func_args))


def process_user_message(messages: list) -> str:
    """Envoie l'historique de conversation au modèle, gère les éventuels tool calls
    et retourne la réponse finale de l'assistant (texte)."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=TOOLS_SCHEMA,
        tool_choice="auto"
    )

    response_message = response.choices[0].message

    # Vérification si le modèle souhaite exécuter une ou plusieurs fonctions (Tool Call)
    if response_message.tool_calls:
        messages.append(response_message)  # Conserve le contexte

        for tool_call in response_message.tool_calls:
            function_result = _execute_tool_call(tool_call)

            # Renvoi du résultat de la fonction au modèle
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": function_result
            })

        # Deuxième appel pour synthétiser la réponse finale à partir des résultats d'outils
        final_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=TOOLS_SCHEMA
        )
        bot_reply = final_response.choices[0].message.content
    else:
        bot_reply = response_message.content

    messages.append({"role": "assistant", "content": bot_reply})
    return bot_reply


def run_monika():
    """Lance la boucle interactive de l'assistant Monika dans le terminal."""
    print("🤖 Monika Initialisé. Comment puis-je vous aider ? (tapez 'exit' pour quitter)")
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