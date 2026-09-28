"""Selección del resultado de búsqueda que corresponde al equipo de Telcel."""
import re
from typing import List, Sequence, Set, Tuple, TypeVar

from app.enrichment.naming import mentions_network

MIN_NAME_SIMILARITY = 0.5
_IGNORED_TOKENS = {"4g", "5g", "lte"}
# Variantes regionales que no se venden en México; se prefieren las globales cuando empatan.
_REGIONAL_TOKENS = {"india", "china", "japan", "usa", "korea"}

T = TypeVar("T")


def name_tokens(text: str) -> Set[str]:
    text = text.lower().replace("+", " plus ")
    return {token for token in re.split(r"[^a-z0-9]+", text) if token and token not in _IGNORED_TOKENS}


def _model_numbers(tokens: Set[str]) -> Set[str]:
    return {token for token in tokens if any(char.isdigit() for char in token)}


def rank_candidates(query: str, telcel_name: str, candidates: Sequence[Tuple[str, T]]) -> List[Tuple[float, T]]:
    """Ordena (nombre, valor) por similitud de tokens con la consulta; descarta los poco parecidos."""
    query_tokens = name_tokens(query)
    wants_5g = mentions_network(telcel_name, "5G")
    ranked = []
    query_model_numbers = _model_numbers(query_tokens)
    for candidate_name, value in candidates:
        candidate_tokens = name_tokens(candidate_name)
        regional = candidate_tokens & _REGIONAL_TOKENS
        candidate_tokens -= regional
        # "V25" y "V27" o "12" y "12C" son equipos distintos aunque el resto del nombre coincida.
        if _model_numbers(candidate_tokens) != query_model_numbers:
            continue
        union = query_tokens | candidate_tokens
        score = len(query_tokens & candidate_tokens) / len(union) if union else 0.0
        if mentions_network(candidate_name, "5G") != wants_5g:
            score -= 0.05
        if regional:
            score -= 0.1
        if score >= MIN_NAME_SIMILARITY:
            ranked.append((score, value))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked
