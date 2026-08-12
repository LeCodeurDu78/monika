"""
tools/weather_tools.py
-----------------------
Outil de récupération de la météo via le service léger wttr.in.
"""

import requests


def get_weather(city: str) -> str:
    """Récupère la météo actuelle via le service léger wttr.in."""
    try:
        # Service gratuit wttr.in au format JSON (pas besoin de clé API externe)
        url = f"https://wttr.in/{city}?format=j1"
        response = requests.get(url, timeout=5)
        data = response.json()

        current = data["current_condition"][0]
        temp = current["temp_C"]
        desc = current["lang_fr"][0]["value"] if "lang_fr" in current else current["weatherDesc"][0]["value"]
        humidity = current["humidity"]

        return f"Météo à {city} : {temp}°C, {desc}, humidité {humidity}%."
    except Exception as e:
        return f"Erreur lors de la récupération de la météo pour {city} : {str(e)}"
