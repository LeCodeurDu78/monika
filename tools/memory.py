"""
tools/memory.py
----------------
Gestion de la mémoire persistant à long terme pour Monika avec SQLite.
Permet d'enregistrer et de rechercher des faits, préférences et chemins importants.
"""

import os
import sqlite3

DB_PATH = os.path.expanduser("~/.config/monika/memory.db")


def _init_db():
    """Initialise la table de mémoire si elle n'existe pas."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def memory_control(action: str, key: str = "", value: str = "", category: str = "general") -> str:
    """Gère la mémoire persistant à long terme de Monika.

    Actions disponibles:
    - 'save' : Enregistre une information (requiert 'key' et 'value').
    - 'search' : Recherche des informations par mot-clé dans la base.
    - 'list' : Affiche l'ensemble des mémoires enregistrées.
    """
    _init_db()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "save":
                if not key or not value:
                    return "Erreur : 'key' et 'value' sont requis pour enregistrer une information."
                cursor.execute("""
                    INSERT INTO memories (category, key, value)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value, category=excluded.category
                """, (category, key.strip().lower(), value.strip()))
                conn.commit()
                return f"🧠 Mémoire enregistrée avec succès : [{key}] = {value}"

            elif action == "search":
                query_str = f"%{key.strip().lower()}%"
                cursor.execute("""
                    SELECT category, key, value FROM memories
                    WHERE key LIKE ? OR value LIKE ? OR category LIKE ?
                """, (query_str, query_str, query_str))
                rows = cursor.fetchall()

                if not rows:
                    return f"Aucune mémoire trouvée pour '{key}'."

                results = [f"• [{cat}] {k} : {v}" for cat, k, v in rows]
                return "Résultats de la mémoire persistant :\n" + "\n".join(results)

            elif action == "list":
                cursor.execute("SELECT category, key, value FROM memories ORDER BY category")
                rows = cursor.fetchall()

                if not rows:
                    return "La mémoire de Monika est actuellement vide."

                results = [f"• [{cat}] {k} : {v}" for cat, k, v in rows]
                return "Contenu complet de la mémoire :\n" + "\n".join(results)

            return "Action non reconnue pour l'outil memory_control."

    except Exception as e:
        return f"Erreur lors de l'accès à la mémoire : {str(e)}"