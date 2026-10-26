"""Entity resolution package for identity deduplication and embedding."""

from src.entity_resolution.embedder import (
    build_person_profile_text,
    embed_person,
    embed_text,
    get_embedder,
)
from src.entity_resolution.resolver import (
    calculate_name_similarity,
    cosine_similarity,
    extract_normalized_orgs,
    normalize_org_name,
    resolve_person,
)

__all__ = [
    "build_person_profile_text",
    "calculate_name_similarity",
    "cosine_similarity",
    "embed_person",
    "embed_text",
    "extract_normalized_orgs",
    "get_embedder",
    "normalize_org_name",
    "resolve_person",
]
