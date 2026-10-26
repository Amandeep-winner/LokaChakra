from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from src.config import settings

_driver: Optional[AsyncDriver] = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


@asynccontextmanager
async def get_neo4j_session() -> AsyncGenerator[AsyncSession, None]:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        yield session


async def verify_neo4j_connectivity() -> bool:
    try:
        driver = get_neo4j_driver()
        await driver.verify_connectivity()
        return True
    except Exception:
        return False
