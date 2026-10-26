import asyncio
from typing import Optional, AsyncGenerator
from contextlib import asynccontextmanager
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from src.config import settings

_driver: Optional[AsyncDriver] = None
_driver_loop: Optional[asyncio.AbstractEventLoop] = None


def get_neo4j_driver() -> AsyncDriver:
    global _driver, _driver_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _driver is None or (_driver_loop is not None and (_driver_loop.is_closed() or _driver_loop != current_loop)):
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
        _driver_loop = current_loop
    return _driver


async def close_neo4j_driver() -> None:
    global _driver, _driver_loop
    if _driver is not None:
        try:
            await _driver.close()
        except Exception:
            pass
        _driver = None
        _driver_loop = None


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
