"""Utilitaires SQLite."""

import os
import sqlite3
from pathlib import Path
from typing import Union

from core.settings import settings


def db_path(filename: str) -> str:
    """Chemin d'une base SQLite."""
    return str(settings.APP_DIR / filename)


def get_connection(path: Union[str, Path]) -> sqlite3.Connection:
    """Ouvre une connexion SQLite."""
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    return sqlite3.connect(str(path))


def init_table(path: Union[str, Path], create_sql: str) -> None:
    """Exécute un script de création de schéma."""
    with get_connection(path) as conn:
        conn.executescript(create_sql)
        conn.commit()
