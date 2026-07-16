"""Flush stale/bad translation cache entries from MongoDB."""

import asyncio
import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


async def flush_translation_cache(mongo_url: str = None, db_name: str = None):
    """Remove all cached translations to force fresh translations."""
    mongo_url = mongo_url or os.environ.get("MONGO_URL")
    db_name = db_name or os.environ.get("DB_NAME", "realaicoach")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    result = await db.translation_cache.delete_many({})
    count = result.deleted_count
    logger.info(f"Flushed {count} translation cache entries")
    print(f"Flushed {count} translation cache entries")

    client.close()
    return count


if __name__ == "__main__":
    asyncio.run(flush_translation_cache())
