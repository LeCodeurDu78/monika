"""
tools/registry.py
-----------------
Registre global des outils de Monika + chargement dynamique des outils personnalisés.
"""

import os
import sys
import importlib
import inspect

from tools.system_tools import open_application, system_control, get_system_stats
from tools.weather_tools import get_weather
from tools.file_tools import manage_files
from tools.email_tools import email_control
from tools.search_tools import web_search
from tools.calendar import calendar_control
from tools.project import create_full_project
from tools.terminal import run_script
from tools.memory import memory_control
from tools.vision_tools import analyze_image
from tools.meta_tools import create_custom_tool

# Registre de base des fonctions Python exécutables
AVAILABLE_TOOLS = {
    "open_application": open_application,
    "get_weather": get_weather,
    "manage_files": manage_files,
    "system_control": system_control,
    "email_control": email_control,
    "web_search": web_search,
    "get_system_stats": get_system_stats,
    "calendar_control": calendar_control,
    "create_full_project": create_full_project,
    "run_script": run_script,
    "memory_control": memory_control,
    "analyze_image": analyze_image,
    "create_custom_tool": create_custom_tool,
}


def _generate_schema_from_func(func, name: str, description: str) -> dict:
    """Génère automatiquement le schéma JSON OpenAI pour une fonction donnée."""
    sig = inspect.signature(func)
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        param_type = "string"
        if param.annotation == int:
            param_type = "integer"
        elif param.annotation == float:
            param_type = "number"
        elif param.annotation == bool:
            param_type = "boolean"

        properties[param_name] = {
            "type": param_type,
            "description": f"Paramètre {param_name}"
        }
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }
    }


def sync_custom_tools(target_schema_list: list):
    """Parcourt le dossier tools/custom/, charge les fonctions Python dans AVAILABLE_TOOLS

    et injecte leurs schémas JSON directement dans target_schema_list.
    """
    custom_dir = os.path.join(os.path.dirname(__file__), "custom")
    if not os.path.exists(custom_dir):
        return

    if custom_dir not in sys.path:
        sys.path.append(custom_dir)

    for filename in os.listdir(custom_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            tool_name = filename[:-3]
            try:
                module_name = f"tools.custom.{tool_name}"
                if module_name in sys.modules:
                    module = importlib.reload(sys.modules[module_name])
                else:
                    module = importlib.import_module(module_name)

                if hasattr(module, tool_name):
                    func = getattr(module, tool_name)
                    # 1. Enregistrement de l'exécutable
                    AVAILABLE_TOOLS[tool_name] = func

                    # 2. Ajout au schéma si pas encore présent
                    if not any(s.get("function", {}).get("name") == tool_name for s in target_schema_list):
                        doc = func.__doc__ or f"Outil personnalisé {tool_name}"
                        target_schema_list.append(_generate_schema_from_func(func, tool_name, doc.strip()))
                        print(f"🧩 [Outil Personnalisé Chargé] : {tool_name}")
            except Exception as e:
                print(f"⚠️ Impossible de charger l'outil personnalisé {tool_name} : {e}")