"""Veille de sujets : liste stockée en SQLite (et non plus figée dans config.py), que Monika peut
modifier elle-même via l'outil `topic_watch_control` (ajout/suppression/liste, ex: "surveille les
sorties de la PS6" ou "arrête de surveiller le bitcoin"). Chaque sujet est recherché une fois par
jour via l'outil de recherche web existant (web_search/DuckDuckGo), et n'est signalé comme
nouveauté que si le contenu retourné a changé depuis la dernière vérification (empreinte comparée
d'un jour sur l'autre) — pas de bruit si rien de neuf n'est trouvé. Intégrée au briefing du matin
(voir tools/utils/briefing_tools.py) plutôt que déclenchée séparément.

Limite assumée : la détection de nouveauté est une comparaison de contenu (pas un jugement de
pertinence par LLM), donc un simple réordonnancement des résultats peut occasionnellement
déclencher une alerte. C'est un compromis volontaire pour rester simple et peu coûteux, à exécuter
une fois par jour."""

import hashlib

from core.db import db_path, get_connection, init_table
from tools.utils.search_tools import web_search

DB_PATH = db_path("topic_watch.db")

_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS watched_topics (
        topic TEXT PRIMARY KEY,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS topic_watch_state (
        topic TEXT PRIMARY KEY,
        last_hash TEXT,
        last_checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
"""


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _fingerprint(result_text: str) -> str:
    return hashlib.sha256(result_text.encode("utf-8")).hexdigest()


def _get_last_hash(cursor, topic: str) -> str | None:
    cursor.execute("SELECT last_hash FROM topic_watch_state WHERE topic = ?", (topic,))
    row = cursor.fetchone()
    return row[0] if row else None


def _store_hash(cursor, topic: str, fingerprint: str) -> None:
    cursor.execute(
        """INSERT INTO topic_watch_state (topic, last_hash, last_checked_at)
           VALUES (?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(topic) DO UPDATE SET
               last_hash = excluded.last_hash, last_checked_at = CURRENT_TIMESTAMP""",
        (topic, fingerprint),
    )


def topic_watch_control(action: str, topic: str = "") -> str:
    """Gère la liste des sujets surveillés quotidiennement par Monika (ajout, suppression, liste)."""
    _init_db()

    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "add":
                if not topic.strip():
                    return "Erreur : 'topic' est requis pour ajouter un sujet à surveiller."
                cursor.execute(
                    "INSERT OR IGNORE INTO watched_topics (topic) VALUES (?)", (topic.strip(),)
                )
                conn.commit()
                return f"🔎 Sujet ajouté à la veille quotidienne : « {topic.strip()} »."

            elif action == "remove":
                if not topic.strip():
                    return "Erreur : 'topic' est requis pour retirer un sujet surveillé (voir action='list')."
                cursor.execute("DELETE FROM watched_topics WHERE topic = ?", (topic.strip(),))
                cursor.execute("DELETE FROM topic_watch_state WHERE topic = ?", (topic.strip(),))
                conn.commit()
                if cursor.rowcount == 0:
                    return f"Aucun sujet surveillé nommé « {topic.strip()} »."
                return f"🗑️ Sujet retiré de la veille : « {topic.strip()} »."

            elif action == "list":
                cursor.execute("SELECT topic FROM watched_topics ORDER BY added_at")
                rows = cursor.fetchall()
                if not rows:
                    return "Aucun sujet actuellement surveillé."
                return "Sujets surveillés quotidiennement :\n" + "\n".join(f"• {r[0]}" for r in rows)

            return "Action non reconnue pour l'outil topic_watch_control (utilise 'add', 'remove' ou 'list')."

    except Exception as e:
        return f"Erreur lors de la gestion des sujets surveillés : {str(e)}"


def check_watched_topics() -> str:
    """Vérifie chaque sujet surveillé et retourne un texte d'alerte pour les seuls sujets où du
    contenu nouveau est apparu depuis la dernière vérification (chaîne vide si rien de neuf, ou si
    aucun sujet n'est surveillé)."""
    _init_db()

    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT topic FROM watched_topics")
        topics = [row[0] for row in cursor.fetchall()]

        if not topics:
            return ""

        alerts: list[str] = []
        for topic in topics:
            try:
                result_text = web_search(source="duckduckgo", query=topic)
            except Exception as e:
                print(f"⚠️ [topic_watch] Échec de la recherche pour « {topic} » : {e}")
                continue

            fingerprint = _fingerprint(result_text)
            previous_hash = _get_last_hash(cursor, topic)
            _store_hash(cursor, topic, fingerprint)

            # Premier passage sur ce sujet : on établit juste la référence, sans alerter tout de suite.
            if previous_hash is not None and fingerprint != previous_hash:
                alerts.append(f"🔎 Nouveauté détectée sur « {topic} » :\n{result_text}")

        conn.commit()

    return "\n\n".join(alerts)


__all__ = ["topic_watch_control", "check_watched_topics"]
