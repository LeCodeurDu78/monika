"""Recherche en ligne."""

import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests
import wikipedia
from ddgs import DDGS

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=fr&gl=FR&ceid=FR:fr"

# Domaines privilégiés selon le mode, injectés dans la requête DuckDuckGo via l'opérateur 'site:'.
_PRICE_SITES = ["amazon.fr", "cdiscount.com", "fnac.com", "ldlc.com", "boulanger.com"]
_COMPARE_SITES = ["lesnumeriques.com", "clubic.com", "01net.com", "commentcamarche.net"]


def _fetch_news(query: str, max_results: int = 5) -> str:
    """Actualités récentes pour `query` via le flux RSS de Google News."""
    url = _GOOGLE_NEWS_RSS.format(query=quote_plus(query))
    response = requests.get(url, timeout=10)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    items = root.findall("./channel/item")[:max_results]
    if not items:
        return f"Aucune actualité récente trouvée pour '{query}'."

    formatted = []
    for item in items:
        title = item.findtext("title", default="Sans titre")
        link = item.findtext("link", default="")
        pub_date = item.findtext("pubDate", default="")
        source_name = item.findtext("source", default="")
        header = f"• {title}" + (f" ({source_name})" if source_name else "")
        formatted.append(f"{header}\n  {pub_date}\n  Lien: {link}")

    return f"Actualités pour '{query}' :\n" + "\n\n".join(formatted)


def _fetch_web(query: str, max_results: int = 3) -> str:
    """Recherche web générale via DuckDuckGo (comportement d'origine de l'outil)."""
    with DDGS() as ddgs:
        results = list(ddgs.text(query, max_results=max_results))

    if not results:
        return f"Aucun résultat trouvé sur le Web pour '{query}'."

    formatted = []
    for r in results:
        title = r.get("title", "Sans titre")
        snippet = r.get("body", "")
        link = r.get("href", "")
        formatted.append(f"• {title}\n  {snippet}\n  Lien: {link}")

    return f"Résultats Web pour '{query}' :\n" + "\n\n".join(formatted)


def _fetch_research(query: str) -> str:
    """Recherche approfondie : résumé encyclopédique (si une page existe) + davantage de résultats web."""
    parts = []
    try:
        summary = wikipedia.summary(query, sentences=3, auto_suggest=True)
        parts.append(f"Contexte (Wikipédia) :\n{summary}")
    except Exception:
        pass  # Pas de page Wikipédia correspondante : on continue avec le web seul.

    parts.append(_fetch_web(query, max_results=6))
    return "\n\n".join(parts)


def _build_targeted_query(query: str, mode: str) -> tuple[str, int]:
    """Adapte la requête et le nombre de résultats pour les modes 'price'/'compare'/'search'."""
    if mode == "price":
        sites = " OR ".join(f"site:{s}" for s in _PRICE_SITES)
        return f"{query} prix ({sites})", 5
    if mode == "compare":
        sites = " OR ".join(f"site:{s}" for s in _COMPARE_SITES)
        return f"{query} comparatif avis ({sites})", 5
    return query, 3  # "search" (par défaut) : requête et nombre de résultats inchangés


def web_search(source: str, query: str, mode: str = "search") -> str:
    """Effectue des recherches sur Wikipédia ou sur le Web. `mode` adapte la requête et la source
    privilégiée pour 'duckduckgo' : actualités (RSS), recherche approfondie, prix, comparatif, ou
    recherche générale."""
    query_clean = query.strip()

    try:
        if source == "wikipedia":
            summary = wikipedia.summary(query_clean, sentences=2, auto_suggest=True)
            return f"Résultat Wikipédia pour '{query_clean}' :\n{summary}"

        if source != "duckduckgo":
            return "Source de recherche non reconnue (utilisez 'wikipedia' ou 'duckduckgo')."

        if mode == "news":
            return _fetch_news(query_clean)
        if mode == "research":
            return _fetch_research(query_clean)

        adapted_query, max_results = _build_targeted_query(query_clean, mode)
        return _fetch_web(adapted_query, max_results)

    except wikipedia.exceptions.DisambiguationError as e:
        options = ", ".join(e.options[:5])
        return f"La recherche '{query}' est ambiguë. Options possibles : {options}."
    except wikipedia.exceptions.PageError:
        return f"Aucune page Wikipédia trouvée pour '{query}'."
    except requests.RequestException as e:
        return f"Erreur réseau lors de la recherche d'actualités : {str(e)}"
    except ET.ParseError:
        return f"Erreur lors de l'analyse des actualités reçues pour '{query}'."
    except Exception as e:
        return f"Erreur lors de la recherche : {str(e)}"