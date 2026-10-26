"""Graphiti hybrid episodic ingestion and semantic search service.

Integrates Graphiti with the native Neo4j instance to enable episodic semantic search
alongside deterministic Cypher structural queries.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional
import structlog

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from src.config import settings

logger = structlog.get_logger(__name__)


class GraphitiService:
    """Wrapper around Graphiti for episodic semantic memory and search."""

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        graphiti_client: Optional[Graphiti] = None,
    ) -> None:
        self.uri = uri or settings.NEO4J_URI
        self.user = user or settings.NEO4J_USER
        self.password = password or settings.NEO4J_PASSWORD
        self._client: Optional[Graphiti] = graphiti_client

    def get_client(self) -> Graphiti:
        """Lazily initialize or return the Graphiti client instance."""
        if self._client is None:
            self._client = Graphiti(
                uri=self.uri,
                user=self.user,
                password=self.password,
            )
        return self._client

    async def initialize(self) -> None:
        """Build constraints and indices for the Graphiti graph layer."""
        try:
            client = self.get_client()
            await client.build_indices_and_constraints()
            logger.info("Graphiti indices and constraints verified successfully")
        except Exception as exc:
            logger.warning("Graphiti initialization encountered notice", error=str(exc))

    async def add_episode(
        self,
        name: str,
        body: str,
        source_description: str = "voice_or_text_episode",
        reference_time: Optional[datetime] = None,
        source: EpisodeType = EpisodeType.message,
    ) -> Any:
        """Ingest a raw episode text into Graphiti episodic memory."""
        client = self.get_client()
        ref_time = reference_time or datetime.now(timezone.utc)
        return await client.add_episode(
            name=name,
            episode_body=body,
            source_description=source_description,
            reference_time=ref_time,
            source=source,
        )

    async def search(
        self,
        query: str,
        num_results: int = 10,
        center_node_uuid: Optional[str] = None,
    ) -> List[Any]:
        """Perform semantic hybrid search across the ingested graph."""
        client = self.get_client()
        return await client.search(
            query=query,
            center_node_uuid=center_node_uuid,
            num_results=num_results,
        )

    async def close(self) -> None:
        """Close client connections cleanly."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:
                logger.warning("Error closing Graphiti client", error=str(exc))
            finally:
                self._client = None
