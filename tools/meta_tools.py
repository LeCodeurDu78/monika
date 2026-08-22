"""Permet à Monika de créer et d'enregistrer de nouveaux outils Python à la volée."""

import os
import sys
import ast
import io
import traceback

CUSTOM_TOOLS_DIR = os.path.join(os.path.dirname(__file__), "custom")
os.makedirs(CUSTOM_TOOLS_DIR, exist_ok=True)

if CUSTOM_TOOLS_DIR not in sys.path:
    sys.path.append(CUSTOM_TOOLS_DIR)

MAX_SELF_CORRECTION_ATTEMPTS = 3

CORRECTION_SYSTEM_PROMPT = (
    "Tu es un correcteur de code Python expert. On te donne un outil Python "
    "destiné à être appelé automatiquement par un agent IA (Monika), qui a "
    "échoué à la validation, avec le message d'erreur exact obtenu.\n\n"
    "Corrige le code pour que l'erreur disparaisse, en conservant son "
    "objectif fonctionnel et sa signature autant que possible.\n\n"
    "Règles strictes, à respecter impérativement :\n"
    "1. Le code doit définir une fonction Python nommée EXACTEMENT "
    "'{tool_name}' (au niveau module, pas imbriquée).\n"
    "2. Le code doit être autonome (tous les imports nécessaires inclus).\n"
    "3. Réponds UNIQUEMENT avec le code Python corrigé complet. Aucune "
    "explication, aucun texte avant ou après, aucune balise markdown/```."
)


def _strip_code_fences(text: str) -> str:
    """Retire d'éventuelles balises ```python ... ``` si le modèle en a ajouté malgré la consigne."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped.strip()


def _defines_function(tree: ast.AST, tool_name: str) -> bool:
    """Vérifie que le code définit bien, au niveau module, une fonction (sync ou async) nommée `tool_name`."""
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == tool_name
        for node in ast.iter_child_nodes(tree)
    )


def _pyflakes_check(python_code: str, filename: str) -> str:
    """Analyse statique optionnelle (variables non définies, imports morts, etc.), sans exécuter le code."""
    try:
        from pyflakes.api import check
        from pyflakes.reporter import Reporter
    except ImportError:
        return ""

    out, err = io.StringIO(), io.StringIO()
    check(python_code, filename, reporter=Reporter(out, err))
    report = (out.getvalue() + err.getvalue()).strip()
    return report


def _validate_tool_code(tool_name: str, python_code: str) -> str | None:
    """Valide le code d'un outil sans l'exécuter réellement (pas d'appel de la fonction elle-même, pour éviter tout effet de bord pendant la validation)."""
    filename = f"{tool_name}.py"

    try:
        tree = ast.parse(python_code, filename=filename)
    except SyntaxError as e:
        return f"Erreur de syntaxe : {e.msg} (ligne {e.lineno}, colonne {e.offset})"

    if not _defines_function(tree, tool_name):
        return (
            f"Le code ne définit aucune fonction nommée exactement '{tool_name}' "
            "au niveau du module (vérifie l'orthographe et l'indentation)."
        )

    flake_report = _pyflakes_check(python_code, filename)
    if flake_report:
        return f"Analyse statique (pyflakes) a détecté des problèmes :\n{flake_report}"

    module_namespace = {"__name__": f"tools.custom._validate_{tool_name}", "__file__": filename}
    try:
        code_obj = compile(python_code, filename, "exec")
        exec(code_obj, module_namespace)
    except Exception:
        tb = traceback.format_exc(limit=5)
        return f"Erreur au chargement du module :\n{tb}"

    func = module_namespace.get(tool_name)
    if not callable(func):
        return f"'{tool_name}' est défini mais n'est pas une fonction appelable."

    return None


def _self_correct_code(tool_name: str, description: str, python_code: str, error: str) -> str | None:
    """Demande au modèle de corriger le code fautif à partir de l'erreur de validation."""
    from config import client, MODEL_NAME

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": CORRECTION_SYSTEM_PROMPT.format(tool_name=tool_name),
                },
                {
                    "role": "user",
                    "content": (
                        f"Description de l'outil : {description}\n\n"
                        f"Code actuel (défaillant) :\n{python_code}\n\n"
                        f"Erreur de validation obtenue :\n{error}"
                    ),
                },
            ],
        )
        corrected = response.choices[0].message.content or ""
        corrected = _strip_code_fences(corrected)
        return corrected or None
    except Exception:
        return None


def create_custom_tool(tool_name: str, python_code: str, description: str) -> str:
    """Crée et enregistre un nouvel outil Python réutilisable pour Monika."""
    from tools.registry import TOOLS_SCHEMA, sync_custom_tools

    current_code = python_code
    attempts_log = []

    for attempt in range(1, MAX_SELF_CORRECTION_ATTEMPTS + 1):
        error = _validate_tool_code(tool_name, current_code)

        if error is None:
            try:
                file_path = os.path.join(CUSTOM_TOOLS_DIR, f"{tool_name}.py")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f'"""\n{description}\n"""\n\n')
                    f.write(current_code)

                sync_custom_tools(TOOLS_SCHEMA)

                if attempt == 1:
                    return f"✅ Outil '{tool_name}' créé, enregistré et immédiatement disponible !"
                return (
                    f"✅ Outil '{tool_name}' créé et enregistré après auto-correction "
                    f"({attempt - 1} correction(s) automatique(s) suite à : "
                    f"{attempts_log[-1].splitlines()[0]})."
                )
            except Exception as e:
                return f"❌ Échec de l'écriture de l'outil validé : {str(e)}"

        attempts_log.append(error)
        print(
            f"🔧 [Auto-correction] Tentative {attempt}/{MAX_SELF_CORRECTION_ATTEMPTS} pour '{tool_name}' — erreur détectée :\n{error}"
        )

        if attempt == MAX_SELF_CORRECTION_ATTEMPTS:
            break

        corrected = _self_correct_code(tool_name, description, current_code, error)
        if not corrected:
            print(f"⚠️ [Auto-correction] Échec de l'appel de correction pour '{tool_name}', arrêt anticipé.")
            break
        current_code = corrected

    return (
        f"❌ Échec de la création de l'outil '{tool_name}' après {len(attempts_log)} tentative(s) "
        f"d'auto-correction. Rien n'a été enregistré (pour éviter un outil cassé). "
        f"Dernière erreur :\n{attempts_log[-1] if attempts_log else 'inconnue'}"
    )
