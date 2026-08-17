"""
tools/meta_tools.py
-------------------
Permet à Monika de créer et d'enregistrer de nouveaux outils Python à la volée.
"""

import os
import sys
import ast

CUSTOM_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "custom")
os.makedirs(CUSTOM_TOOLS_DIR, exist_ok=True)

if CUSTOM_TOOLS_DIR not in sys.path:
    sys.path.append(CUSTOM_TOOLS_DIR)


def create_custom_tool(tool_name: str, python_code: str, description: str) -> str:
    """Crée et enregistre un nouvel outil Python réutilisable pour Monika.

    Args:
        tool_name: Nom unique de la fonction/outil en snake_case (ex: 'get_btc_price').
        python_code: Code Python complet contenant la fonction avec le même nom que tool_name.
        description: Description claire de ce que fait l'outil.
    """
    from tools.registry import TOOLS_SCHEMA, sync_custom_tools

    try:
        # 1. Validation syntaxique
        try:
            ast.parse(python_code)
        except SyntaxError as syntax_err:
            return f"❌ Erreur de syntaxe dans le code généré : {syntax_err}"

        # 2. Sauvegarde du fichier
        file_path = os.path.join(CUSTOM_TOOLS_DIR, f"{tool_name}.py")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f'"""\n{description}\n"""\n\n')
            f.write(python_code)

        # 3. Synchronisation immédiate (Registre + Schema OpenAI)
        sync_custom_tools(TOOLS_SCHEMA)

        return f"✅ Outil '{tool_name}' créé, enregistré et immédiatement disponible !"

    except Exception as e:
        return f"❌ Échec de la création de l'outil : {str(e)}"