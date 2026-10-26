"""FastEmbed vector embedding utility for entity profiles.

Uses BAAI/bge-small-en-v1.5 to generate normalized 384-dimensional dense vectors
for semantic person profiling and probabilistic entity resolution.
"""

from typing import List, Optional
import os

# Suppress HuggingFace symlink warning on Windows environments
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

from fastembed import TextEmbedding
from src.contracts.schema import ExtractedPerson

_embedder_instance: Optional[TextEmbedding] = None


def get_embedder() -> TextEmbedding:
    """Return or initialize the singleton FastEmbed TextEmbedding model."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
    return _embedder_instance


def build_person_profile_text(p: ExtractedPerson) -> str:
    """Construct a canonical textual profile representation for vector embedding."""
    aliases_str = " ".join(p.aliases) if p.aliases else ""
    alumni_str = " ".join(p.alumni_orgs) if p.alumni_orgs else ""
    return (
        f"{p.full_name} {aliases_str} | Org: {p.current_org or ''} {p.current_role or ''} "
        f"| Alumni: {alumni_str} | City: {p.location_city or ''}"
    ).strip()


def embed_text(text: str) -> List[float]:
    """Generate a 384-dimensional float vector for an arbitrary text string."""
    embedder = get_embedder()
    embeddings = list(embedder.embed([text]))
    return embeddings[0].tolist()


def embed_person(p: ExtractedPerson) -> List[float]:
    """Generate a 384-dimensional float vector for an ExtractedPerson profile."""
    text = build_person_profile_text(p)
    return embed_text(text)
