"""Shared response primitives."""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope for list endpoints.

    ``total`` is the count BEFORE pagination so the UI can show "showing 25 of
    137" and size its pager correctly.
    """

    items: list[T]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    message: str
    ok: bool = True


class CountByKey(BaseModel):
    key: str
    count: int
