"""Shared API contracts and helpers for list endpoints."""

from collections.abc import Callable, Iterable
from datetime import date, datetime
from numbers import Number
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")
SortDirection = Literal["asc", "desc"]


class PaginatedResponse(BaseModel, Generic[T]):
    """Envelope used by dashboard list views when pagination is requested."""

    items: list[T]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    search: str | None = None
    sort_by: str
    sort_dir: SortDirection


def page_items(
    items: Iterable[T],
    *,
    search: str | None,
    search_fields: Iterable[Callable[[T], object]],
    sort_by: str,
    sort_dir: SortDirection,
    sort_fields: dict[str, Callable[[T], object]],
    limit: int,
    offset: int,
) -> PaginatedResponse[T]:
    """Filter, sort, and slice an already authorized list of items."""

    filtered = list(items)
    normalized_search = search.strip().lower() if search else None
    if normalized_search:
        filtered = [
            item
            for item in filtered
            if any(normalized_search in str(field(item) or "").lower() for field in search_fields)
        ]

    sort_key = sort_fields.get(sort_by) or sort_fields["created_at"]
    filtered.sort(key=lambda item: _sortable_value(sort_key(item)), reverse=sort_dir == "desc")

    total = len(filtered)
    return PaginatedResponse(
        items=filtered[offset : offset + limit],
        total=total,
        limit=limit,
        offset=offset,
        search=normalized_search,
        sort_by=sort_by if sort_by in sort_fields else "created_at",
        sort_dir=sort_dir,
    )


def _sortable_value(value: object) -> tuple[int, object]:
    if value is None:
        return (1, "")
    if isinstance(value, bool):
        return (0, int(value))
    if isinstance(value, Number):
        return (0, value)
    if isinstance(value, datetime):
        return (0, value.timestamp())
    if isinstance(value, date):
        return (0, value.toordinal())
    return (0, str(value).lower())
