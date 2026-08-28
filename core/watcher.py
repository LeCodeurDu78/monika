"""Fabrique de threads de fond pour Monika : boucle générique à intervalle fixe, et
spécialisation pour déclencher une action une fois par jour tant que le process principal tourne.

Le trigger quotidien complète le déclenchement natif de l'OS (core.native_scheduler), qui prend
le relais quand le process principal est arrêté. Les deux chemins partagent le même état via
core.wake_store, pour ne jamais exécuter la même journée deux fois."""

import threading
from datetime import datetime
from typing import Callable

from core.wake_store import mark_ran_today, should_run_today

_CHECK_INTERVAL_SECONDS = 60


def start_watcher(interval_seconds: float, tick: Callable[[], None]) -> threading.Event:
    """Démarre un thread démon qui appelle `tick` toutes les `interval_seconds`."""
    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(interval_seconds):
            tick()

    threading.Thread(target=_loop, daemon=True).start()
    return stop_event


def start_daily_trigger(task_key: str, time_of_day: str, action: Callable[[], None]) -> threading.Event:
    """Démarre un watcher qui exécute `action` une fois par jour, dès la première vérification
    suivant `time_of_day` ('HH:MM')."""
    hour, minute = (int(p) for p in time_of_day.split(":"))

    def _tick() -> None:
        now = datetime.now()
        if (now.hour, now.minute) >= (hour, minute) and should_run_today(task_key):
            mark_ran_today(task_key)
            action()

    return start_watcher(_CHECK_INTERVAL_SECONDS, _tick)
