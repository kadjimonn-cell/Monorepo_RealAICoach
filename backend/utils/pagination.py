from __future__ import annotations

from typing import Any, AsyncIterator


DEFAULT_PAGE_SIZE = 1000
MAX_PAGE_SIZE = 5000


def _normalized_page_size(page_size: int | None) -> int:
    size = int(page_size or DEFAULT_PAGE_SIZE)
    if size < 1:
        return DEFAULT_PAGE_SIZE
    return min(size, MAX_PAGE_SIZE)


async def iter_find_paginated(
    collection,
    query: dict[str, Any],
    projection: dict[str, Any] | None = None,
    *,
    sort: list[tuple[str, int]] | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_docs: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    size = _normalized_page_size(page_size)
    offset = 0
    yielded = 0
    capped_max_docs = int(max_docs) if max_docs is not None else None
    if capped_max_docs is not None and capped_max_docs < 1:
        return

    while True:
        if capped_max_docs is not None and yielded >= capped_max_docs:
            break
        batch_size = size
        if capped_max_docs is not None:
            batch_size = min(batch_size, capped_max_docs - yielded)
        cursor = collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        batch = await cursor.skip(offset).limit(batch_size).to_list(batch_size)
        if not batch:
            break
        for row in batch:
            yield row
            yielded += 1
        if len(batch) < size:
            break
        offset += size


async def list_aggregate_paginated(
    collection,
    pipeline: list[dict[str, Any]],
    *,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[dict[str, Any]]:
    size = _normalized_page_size(page_size)
    offset = 0
    rows: list[dict[str, Any]] = []

    while True:
        paged_pipeline = [*pipeline, {"$skip": offset}, {"$limit": size}]
        batch = await collection.aggregate(paged_pipeline).to_list(size)
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < size:
            break
        offset += size

    return rows
