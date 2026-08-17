"""
tools/utils/joke_tools.py
--------------------------
Outil permettant à Monika de raconter des blagues via pyjokes.
"""

import pyjokes


def get_joke(language: str = "fr", category: str = "neutral") -> str:
    """Raconte une blague pour développeur/geek.

    Args:
        language: Langue de la blague ('fr', 'en', 'es', 'de'). Par défaut 'fr'.
        category: Catégorie ('neutral', 'chuck', 'all'). Par défaut 'neutral'.
    """
    try:
        lang = language if language in ["fr", "en", "es", "de"] else "fr"  # langues supportées par pyjokes
        cat = category if category in ["neutral", "chuck", "all"] else "neutral"

        joke = pyjokes.get_joke(language=lang, category=cat)
        return f"😄 {joke}"
    except Exception as e:
        return f"❌ Impossible de récupérer une blague : {e}"