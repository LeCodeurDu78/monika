"""
tools/registry.py
-------------------
Registre central associant le nom de chaque outil (tel que déclaré dans
les schémas OpenAI) à la fonction Python qui l'implémente réellement.
"""

from tools.system_tools import open_application, system_control, get_system_stats
from tools.weather_tools import get_weather
from tools.file_tools import manage_files
from tools.email_tools import email_control
from tools.search_tools import web_search
from tools.calendar import calendar_control
from tools.project import create_full_project
from tools.terminal import run_script
from tools.memory import memory_control

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
}
