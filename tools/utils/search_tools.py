"""Recherche en ligne : Wikipédia (culture générale, définitions) et DuckDuckGo (actualité, recherches Web générales)."""

import wikipedia
from ddgs import DDGS


def web_search(source: str, query: str) -> str:
    """Effectue des recherches sur Wikipédia ou sur l'ensemble du Web via DuckDuckGo."""
    try:
        query_clean = query.strip()

        if source == "wikipedia":
            summary = wikipedia.summary(query_clean, sentences=2, auto_suggest=True)
            return f"Résultat Wikipédia pour '{query_clean}' :\n{summary}"

        elif source == "duckduckgo":
            with DDGS() as ddgs:
                results = list(ddgs.text(query_clean, max_results=3))

            if not results:
                return f"Aucun résultat trouvé sur le Web pour '{query_clean}'."

            formatted_results = []
            for r in results:
                title = r.get("title", "Sans titre")
                snippet = r.get("body", "")
                link = r.get("href", "")
                formatted_results.append(f"• {title}\n  {snippet}\n  Lien: {link}")

            return f"Résultats Web pour '{query_clean}' :\n" + "\n\n".join(formatted_results)

        return "Source de recherche non reconnue (utilisez 'wikipedia' ou 'duckduckgo')."

    except wikipedia.exceptions.DisambiguationError as e:
        options = ", ".join(e.options[:5])
        return f"La recherche '{query}' est ambiguë. Options possibles : {options}."
    except wikipedia.exceptions.PageError:
        return f"Aucune page Wikipédia trouvée pour '{query}'."
    except Exception as e:
        return f"Erreur lors de la recherche : {str(e)}"
