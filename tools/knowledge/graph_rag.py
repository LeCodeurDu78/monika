"""Graph RAG (graphe de connaissances)."""

import json
import os
import sqlite3
from typing import Optional

import numpy as np

from tools.knowledge.memory import embed_text, blob_to_embedding, cosine_similarity
from tools.knowledge.rag_tools import DB_PATH as RAG_DB_PATH
from core.db import db_path, get_connection, init_table

DB_PATH = db_path("graph.db")


GRAPH_BACKFILL_BATCH_SIZE = 15


GRAPH_SEED_TOP_K = 5
GRAPH_SEED_MIN_SIMILARITY = 0.35


GRAPH_MAX_HOPS = 2
GRAPH_MAX_RELATIONS = 25

EXTRACTION_SYSTEM_PROMPT = (
    "Tu extrais des entités et des relations d'un texte pour construire un "
    "graphe de connaissances. Réponds UNIQUEMENT avec un objet JSON valide, "
    "sans aucun texte avant/après, sans balise markdown/```.\n\n"
    "Format exact attendu :\n"
    '{"entities": [{"name": "...", "type": "..."}], '
    '"relations": [{"from": "...", "relation": "...", "to": "..."}]}\n\n'
    "Règles :\n"
    "1. 'name' : forme courte et normalisée de l'entité (ex: 'Adam', pas "
    "'l'utilisateur Adam mentionné plus haut').\n"
    "2. 'type' : catégorie courte (ex: personne, projet, outil, lieu, "
    "organisation, concept, date, autre).\n"
    "3. 'relation' : verbe ou courte expression au présent (ex: 'travaille "
    "sur', 'recommande', 'dépend de', 'habite à').\n"
    "4. 'from' et 'to' doivent correspondre exactement à un 'name' présent "
    "dans 'entities'.\n"
    "5. N'invente rien : si le texte ne contient pas d'entités/relations "
    "claires, réponds avec des listes vides.\n"
    "6. Limite-toi à ce qui est explicitement dans le texte, pas d'inférence "
    "spéculative."
)


_CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL COLLATE NOCASE,
        entity_type TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name COLLATE NOCASE)
    );
    CREATE TABLE IF NOT EXISTS relations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_entity_id INTEGER NOT NULL REFERENCES entities(id),
        relation TEXT NOT NULL,
        to_entity_id INTEGER NOT NULL REFERENCES entities(id),
        source TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS processed_chunks (
        source TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (source, chunk_index)
    );
    CREATE INDEX IF NOT EXISTS idx_relations_from ON relations(from_entity_id);
    CREATE INDEX IF NOT EXISTS idx_relations_to ON relations(to_entity_id);
    CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source, chunk_index);
"""


def _init_db() -> None:
    init_table(DB_PATH, _CREATE_SQL)


def _get_or_create_entity(cursor: sqlite3.Cursor, name: str, entity_type: str = "") -> Optional[int]:
    clean_name = name.strip()
    if not clean_name:
        return None

    cursor.execute("SELECT id FROM entities WHERE name = ? COLLATE NOCASE", (clean_name,))
    row = cursor.fetchone()
    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO entities (name, entity_type) VALUES (?, ?)",
        (clean_name, entity_type.strip() if entity_type else None),
    )
    return cursor.lastrowid


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _extract_entities_relations(text: str) -> Optional[dict]:
    """Appelle le LLM pour extraire {entities, relations} d'un chunk de texte."""
    from config import client, MODEL_NAME

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": text[:3000]},
            ],
        )
        raw = response.choices[0].message.content or ""
        raw = _strip_code_fences(raw)
        data = json.loads(raw)

        entities = data.get("entities", [])
        relations = data.get("relations", [])
        if not isinstance(entities, list) or not isinstance(relations, list):
            return None
        return {"entities": entities, "relations": relations}
    except Exception:
        return None


def _backfill_batch(conn: sqlite3.Connection, limit: int = GRAPH_BACKFILL_BATCH_SIZE) -> int:
    """Extrait entités/relations pour les chunks de rag.db pas encore traités."""
    if not os.path.exists(RAG_DB_PATH):
        return 0

    cursor = conn.cursor()
    processed_count = 0

    with get_connection(RAG_DB_PATH) as rag_conn:
        rag_cursor = rag_conn.cursor()
        rag_cursor.execute("SELECT source, chunk_index, content FROM rag_chunks")
        all_chunks = rag_cursor.fetchall()

    for source, chunk_index, content in all_chunks:
        if processed_count >= limit:
            break

        cursor.execute(
            "SELECT 1 FROM processed_chunks WHERE source = ? AND chunk_index = ?",
            (source, chunk_index),
        )
        if cursor.fetchone():
            continue

        extracted = _extract_entities_relations(content)
        processed_count += 1
        cursor.execute(
            "INSERT OR IGNORE INTO processed_chunks (source, chunk_index) VALUES (?, ?)",
            (source, chunk_index),
        )

        if not extracted:
            continue

        entity_ids_by_name = {}
        for entity in extracted["entities"]:
            name = str(entity.get("name", "")).strip()
            if not name:
                continue
            entity_type = str(entity.get("type", "")).strip()
            entity_id = _get_or_create_entity(cursor, name, entity_type)
            if entity_id is not None:
                entity_ids_by_name[name.lower()] = entity_id

        for relation in extracted["relations"]:
            from_name = str(relation.get("from", "")).strip().lower()
            to_name = str(relation.get("to", "")).strip().lower()
            relation_label = str(relation.get("relation", "")).strip()

            from_id = entity_ids_by_name.get(from_name)
            to_id = entity_ids_by_name.get(to_name)
            if not (from_id and to_id and relation_label):
                continue

            cursor.execute(
                "INSERT INTO relations (from_entity_id, relation, to_entity_id, source, chunk_index) VALUES (?, ?, ?, ?, ?)",
                (from_id, relation_label, to_id, source, chunk_index),
            )

    conn.commit()
    return processed_count


def graph_backfill(limit: int = 200) -> str:
    """Force un backfill complet (ou jusqu'à `limit` chunks) : à utiliser après une grosse indexation RAG plutôt que d'attendre que les recherches..."""
    _init_db()
    with get_connection(DB_PATH) as conn:
        count = _backfill_batch(conn, limit=limit)
    if count == 0:
        return "Aucun nouveau chunk à traiter : le graphe de connaissances est déjà à jour."
    return f"🕸️ Backfill terminé : {count} chunk(s) analysé(s) et intégré(s) au graphe de connaissances."


def _semantic_seed_chunks(query_embedding: np.ndarray) -> list[tuple[str, int, float]]:
    """Renvoie les (source, chunk_index, similarité) des chunks rag.db les plus proches de la question — ce sont les points d'entrée dans le graphe."""
    if not os.path.exists(RAG_DB_PATH):
        return []

    with get_connection(RAG_DB_PATH) as rag_conn:
        rag_cursor = rag_conn.cursor()
        rag_cursor.execute(
            "SELECT source, chunk_index, embedding FROM rag_chunks WHERE embedding IS NOT NULL"
        )
        rows = rag_cursor.fetchall()

    scored = []
    for source, chunk_index, blob in rows:
        similarity = cosine_similarity(query_embedding, blob_to_embedding(blob))
        if similarity >= GRAPH_SEED_MIN_SIMILARITY:
            scored.append((source, chunk_index, similarity))

    scored.sort(key=lambda row: row[2], reverse=True)
    return scored[:GRAPH_SEED_TOP_K]


def _entities_from_chunks(cursor: sqlite3.Cursor, chunks: list[tuple[str, int, float]]) -> dict[int, str]:
    """Entités liées aux chunks trouvés par similarité sémantique (portes d'entrée dans le graphe)."""
    entity_ids: dict[int, str] = {}
    for source, chunk_index, _ in chunks:
        cursor.execute(
            """
            SELECT e.id, e.name FROM relations r
            JOIN entities e ON e.id = r.from_entity_id OR e.id = r.to_entity_id
            WHERE r.source = ? AND r.chunk_index = ?
            """,
            (source, chunk_index),
        )
        for entity_id, name in cursor.fetchall():
            entity_ids[entity_id] = name
    return entity_ids


def _entities_matching_query(cursor: sqlite3.Cursor, query: str) -> dict[int, str]:
    """Entités directement nommées dans la question (ex: 'Adam', 'Monika'), en complément de la recherche par similarité — utile pour les questions..."""
    cursor.execute("SELECT id, name FROM entities")
    matches = {}
    query_lower = query.lower()
    for entity_id, name in cursor.fetchall():
        if name.lower() in query_lower:
            matches[entity_id] = name
    return matches


def _traverse_graph(
    cursor: sqlite3.Cursor, seed_ids: set[int], max_hops: int = GRAPH_MAX_HOPS
) -> list[tuple]:
    """Traversée en largeur (BFS) du graphe à partir des entités "porte d'entrée", jusqu'à `max_hops` sauts."""
    visited_entities = set(seed_ids)
    frontier = set(seed_ids)
    collected_relation_ids = set()
    relations = []

    for _ in range(max_hops):
        if not frontier or len(relations) >= GRAPH_MAX_RELATIONS:
            break

        placeholders = ",".join("?" * len(frontier))
        cursor.execute(
            f"""
            SELECT r.id, ef.name, r.relation, et.name, r.source, r.chunk_index, r.from_entity_id, r.to_entity_id
            FROM relations r
            JOIN entities ef ON ef.id = r.from_entity_id
            JOIN entities et ON et.id = r.to_entity_id
            WHERE r.from_entity_id IN ({placeholders}) OR r.to_entity_id IN ({placeholders})
            """,
            (*frontier, *frontier),
        )
        rows = cursor.fetchall()

        next_frontier = set()
        for rel_id, from_name, relation, to_name, source, chunk_index, from_id, to_id in rows:
            if rel_id not in collected_relation_ids:
                collected_relation_ids.add(rel_id)
                relations.append((from_name, relation, to_name, source, chunk_index))

            for entity_id in (from_id, to_id):
                if entity_id not in visited_entities:
                    next_frontier.add(entity_id)

        visited_entities |= next_frontier
        frontier = next_frontier

    return relations[:GRAPH_MAX_RELATIONS]


def graph_search(query: str) -> str:
    """Interroge le graphe de connaissances de Monika (entités + relations extraites des documents indexés via rag_control) pour répondre à des questions..."""
    if not query.strip():
        return "Erreur : 'query' est requis pour interroger le graphe de connaissances."

    _init_db()

    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            _backfill_batch(conn, limit=GRAPH_BACKFILL_BATCH_SIZE)

            seed_entities: dict[int, str] = {}

            query_embedding = embed_text(query)
            if query_embedding is not None:
                seed_chunks = _semantic_seed_chunks(query_embedding)
                seed_entities.update(_entities_from_chunks(cursor, seed_chunks))

            seed_entities.update(_entities_matching_query(cursor, query))

            if not seed_entities:
                return (
                    f"Aucune entité ou relation pertinente trouvée dans le graphe de connaissances pour '{query}'. "
                    "Le graphe se construit au fur et à mesure des documents indexés via rag_control(ingest) : "
                    "essaie rag_search pour une recherche par similarité de texte, ou lance graph_backfill après une nouvelle indexation."
                )

            relations = _traverse_graph(cursor, set(seed_entities.keys()))

            if not relations:
                entity_names = ", ".join(sorted(seed_entities.values()))
                return f"Entités trouvées ({entity_names}) mais aucune relation associée dans le graphe pour '{query}'."

            lines = [
                f"• {from_name} —[{relation}]→ {to_name}  (source: {os.path.basename(source)}, chunk {chunk_index})"
                for from_name, relation, to_name, source, chunk_index in relations
            ]
            return "🕸️ Relations trouvées dans le graphe de connaissances :\n\n" + "\n".join(lines)

    except Exception as e:
        return f"Erreur lors de l'accès au graphe de connaissances : {str(e)}"
