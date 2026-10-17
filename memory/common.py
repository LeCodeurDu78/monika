"""Éléments communs aux backends de mémoire de Monika."""


class MemoryUnavailable(RuntimeError):
    """Un backend de mémoire n'est pas utilisable (dépendance absente, serveur éteint, trop lent...)."""


def log(message: str) -> None:
    """Affiche un message de la mémoire dans le terminal (même style que le reste de Monika)."""
    print(message, flush=True)


def truncate(text: str, limit: int) -> str:
    """Coupe `text` à `limit` caractères au plus, en ajoutant « … » si quelque chose a été retiré."""
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def describe_error(exc: BaseException) -> str:
    """Message d'erreur lisible, avec la marche à suivre quand la cause est un module manquant."""
    if isinstance(exc, ModuleNotFoundError):
        return f"module Python manquant « {exc.name} »"
    return f"{type(exc).__name__}: {exc}"
