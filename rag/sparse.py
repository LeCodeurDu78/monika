"""Encodeur sparse de type BM25, sans dépendance externe.

Côté document, on calcule la partie « fréquence du terme » de BM25 (saturation + normalisation par
la longueur). Côté requête, chaque terme vaut 1. La partie IDF est appliquée par Qdrant lui-même
(`Modifier.IDF` sur le vecteur sparse), ce qui la garde à jour au fil des ajouts et suppressions.

Les termes sont hachés en entiers 32 bits (crc32, stable d'une exécution à l'autre, contrairement à
`hash()`). Les identifiants de code sont découpés (snake_case, camelCase) en plus d'être gardés entiers.
"""

import re
import unicodedata
import zlib
from collections import Counter
from typing import Optional

from qdrant_client import models

_WORD = re.compile(r"[^\W_]+")  # suites alphanumériques ; le « _ » sépare donc les mots (snake_case)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_MAX_WORD = 40  # au-delà : hachages, base64, etc.

_STOPWORDS = frozenset(
    """
    le la les un une des du de d l au aux et ou mais donc or ni car que qui quoi dont où ce cet cette ces
    se sa son ses leur leurs mon ma mes ton ta tes notre nos votre vos je tu il elle on nous vous ils elles
    me te lui y en ne pas plus par pour sur sous dans avec sans entre vers chez comme si est sont etre ete
    a ai as avons avez ont avait etait the of and or to in on at by for with from as is are was were be been
    it its this that these those an not no but if then so
    """.split()
)

K1 = 1.2
B = 0.75
AVG_DOC_LEN = 120.0  # longueur moyenne supposée (en termes) : évite de maintenir une statistique globale
_EMPTY_TOKEN = "_vide_"


def _fold(text: str) -> str:
    """Minuscules sans accents (les autres alphabets sont conservés)."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _stem(token: str) -> str:
    """Racinisation minimale : pluriel en « s » (appliquée à l'identique aux documents et aux requêtes)."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD.findall(text):
        if len(word) > _MAX_WORD:
            continue
        parts = _CAMEL.split(word)
        candidates = [word] + parts if len(parts) > 1 else [word]
        for candidate in candidates:
            folded = _fold(candidate)
            if len(folded) < 2 or folded in _STOPWORDS:
                continue
            tokens.append(_stem(folded))
    return tokens


def _index(token: str) -> int:
    return zlib.crc32(token.encode("utf-8"))


def encode_document(text: str) -> models.SparseVector:
    tokens = tokenize(text) or [_EMPTY_TOKEN]
    length_norm = K1 * (1 - B + B * len(tokens) / AVG_DOC_LEN)
    weights: dict[int, float] = {}
    for token, count in Counter(tokens).items():
        idx = _index(token)
        weights[idx] = weights.get(idx, 0.0) + count * (K1 + 1) / (count + length_norm)
    indices = sorted(weights)
    return models.SparseVector(indices=indices, values=[weights[i] for i in indices])


def encode_query(text: str) -> Optional[models.SparseVector]:
    """None si la requête ne contient aucun terme exploitable (la recherche se fait alors en dense seul)."""
    indices = sorted({_index(t) for t in tokenize(text)})
    if not indices:
        return None
    return models.SparseVector(indices=indices, values=[1.0] * len(indices))
