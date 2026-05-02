"""FastAPI query helpers for list endpoints."""

from typing import Annotated

from fastapi import Query

from src.core.entities.pagination import SortDirection


LimitQuery = Annotated[int, Query(ge=1, le=100)]
OffsetQuery = Annotated[int, Query(ge=0)]
SearchQuery = Annotated[str | None, Query(min_length=1, max_length=120)]
SortDirQuery = Annotated[SortDirection, Query(pattern="^(asc|desc)$")]


def wants_paginated_response(paginated: bool) -> bool:
    return paginated
