"""Carnet d'adresses de Monika : contacts Discord (nom -> identifiant), stockés en SQLite (databases/contacts.db)."""

import re
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from core.db import db_path, get_connection, init_table

DB_PATH = db_path("contacts.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS contacts (
        name_key TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        discord_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""

_DISCORD_ID = re.compile(r"^\d{15,22}$")
_initialized = False
_init_lock = threading.Lock()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Connexion SQLite validée (commit) puis fermée ; crée la table au premier usage."""
    global _initialized
    with _init_lock:
        if not _initialized:
            init_table(DB_PATH, _CREATE_SQL)
            _initialized = True
    conn = get_connection(DB_PATH)
    try:
        with conn:  # commit si tout va bien, rollback sinon
            yield conn
    finally:
        conn.close()


def find_contacts(name: str) -> list[tuple[str, str]]:
    """Contacts (nom affiché, identifiant Discord) correspondant à `name`.

    Un nom exact l'emporte ; à défaut, tous les contacts dont le nom contient `name`. L'appelant doit
    traiter le cas de plusieurs résultats (ne jamais envoyer un message au « premier » venu).
    """
    key = name.strip().lower()
    if not key:
        return []
    with _connect() as conn:
        exact = conn.execute(
            "SELECT display_name, discord_id FROM contacts WHERE name_key = ?", (key,)
        ).fetchall()
        if exact:
            return exact
        return conn.execute(
            "SELECT display_name, discord_id FROM contacts WHERE instr(name_key, ?) > 0 ORDER BY name_key",
            (key,),
        ).fetchall()


def manage_contacts(action: str, name: str = "", discord_id: str = "") -> str:
    """Gère le carnet d'adresses de Monika."""
    key = name.strip().lower()

    if action == "add":
        if not key or not discord_id:
            return "❌ Veuillez fournir un nom et un identifiant Discord."
        did = discord_id.strip()
        if not _DISCORD_ID.match(did):
            return (
                "❌ L'identifiant Discord doit être numérique (15 à 22 chiffres). Dans Discord : "
                "Paramètres > Avancés > Mode développeur, puis clic droit sur l'utilisateur > Copier l'identifiant."
            )
        with _connect() as conn:
            existed = conn.execute("SELECT 1 FROM contacts WHERE name_key = ?", (key,)).fetchone() is not None
            conn.execute(
                "INSERT INTO contacts (name_key, display_name, discord_id) VALUES (?, ?, ?) "
                "ON CONFLICT(name_key) DO UPDATE SET display_name = excluded.display_name, "
                "discord_id = excluded.discord_id",
                (key, name.strip(), did),
            )
        verb = "mis à jour" if existed else "enregistré"
        return f"✅ Contact '{name.strip()}' {verb} (Discord {did}) !"

    if action == "get":
        matches = find_contacts(name)
        if not matches:
            return f"❌ Aucun contact trouvé pour '{name}'."
        if len(matches) > 1:
            return f"❓ Plusieurs contacts correspondent à '{name}' : " + ", ".join(m[0] for m in matches) + "."
        return f"📇 Contact trouvé : {matches[0][0]} -> Discord {matches[0][1]}"

    if action == "list":
        with _connect() as conn:
            rows = conn.execute("SELECT display_name, discord_id FROM contacts ORDER BY name_key").fetchall()
        if not rows:
            return "📖 Le carnet d'adresses est vide."
        return "\n".join(["📖 **Carnet d'adresses :**"] + [f"- **{n}** : Discord {i}" for n, i in rows])

    if action == "delete":
        with _connect() as conn:  # suppression : nom exact uniquement
            deleted = conn.execute("DELETE FROM contacts WHERE name_key = ?", (key,)).rowcount
        return f"🗑️ Contact '{name}' supprimé." if deleted else f"❌ Contact '{name}' introuvable."

    return "❌ Action inconnue. Actions valides : 'add', 'get', 'list', 'delete'."
