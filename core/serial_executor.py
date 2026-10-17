"""Exécute des appels les uns après les autres sur UN SEUL thread dédié.

Monika est appelée depuis plusieurs threads (clavier, tâches planifiées, Discord). Or Playwright (API
synchrone) lie ses objets au thread qui les a créés : un navigateur ouvert depuis un thread et utilisé
depuis un autre plante avec « Cannot switch to a different thread ». En faisant passer tous les tours de
l'agent par ce même thread, les outils voient toujours le même thread, et deux tours ne se chevauchent
jamais (pas de course sur l'historique, la mémoire ou le profil du navigateur).
"""

import concurrent.futures
import queue
import threading
from typing import Any, Callable


class SerialExecutor:
    def __init__(self, name: str = "monika-agent") -> None:
        self._name = name
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def _ensure_thread(self) -> None:
        with self._start_lock:
            if self._thread is None or not self._thread.is_alive():
                # daemon : ne bloque pas la fermeture du programme (Ctrl+C pendant un tour).
                self._thread = threading.Thread(target=self._work, daemon=True, name=self._name)
                self._thread.start()

    def _work(self) -> None:
        while True:
            future, fn, args, kwargs = self._queue.get()
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(fn(*args, **kwargs))
            except BaseException as exc:  # noqa: BLE001 - renvoyé tel quel à l'appelant
                future.set_exception(exc)

    def run(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Exécute fn(*args, **kwargs) sur le thread dédié et renvoie son résultat (ou relève son exception)."""
        if self._thread is not None and threading.current_thread() is self._thread:
            return fn(*args, **kwargs)  # appel imbriqué : pas d'attente sur soi-même
        self._ensure_thread()
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._queue.put((future, fn, args, kwargs))
        return future.result()
