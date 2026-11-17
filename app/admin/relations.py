"""Searchable relationship pickers for every model, generated automatically.

For each relationship of a model (many-to-one, one-to-many, many-to-many) we build a
select2 AJAX loader that:
  * lists records as soon as the dropdown opens (no "type 1 character" step),
  * searches the related model's text columns and primary key as you type,
  * pages through large tables (20 at a time, "load more" on scroll).

Everything is plain SQLAlchemy, so it works on any database the app supports.
"""

import re
from typing import Any

from sqladmin.ajax import QueryAjaxModelLoader
from sqlalchemy import Enum, String, Text, cast, inspect, or_, select
from starlette.requests import Request

PAGE_SIZE = 20

# Columns that must never be searchable from a dropdown.
_SENSITIVE = re.compile(r"password|passwd|hash|secret|token|otp|api_?key|access_?key|salt", re.I)

# Preferred columns to label / sort records by, in order.
LABEL_COLUMNS = ("name", "title", "username", "label", "display_name", "full_name", "email", "slug", "code")


def searchable_columns(model: type) -> list[str]:
    """Primary key + non-sensitive text columns of `model` (by attribute key)."""
    mapper = inspect(model)
    fields: list[str] = []
    for prop in mapper.column_attrs:
        column = prop.columns[0]
        if column.primary_key:
            fields.append(prop.key)
        elif isinstance(column.type, (String, Text, Enum)) and not _SENSITIVE.search(prop.key):
            fields.append(prop.key)
    return fields


def label_column(model: type) -> str | None:
    keys = {prop.key for prop in inspect(model).column_attrs}
    return next((name for name in LABEL_COLUMNS if name in keys), None)


def auto_ajax_refs(model: type) -> dict[str, dict[str, Any]]:
    """`form_ajax_refs` config for every relationship of `model`."""
    refs: dict[str, dict[str, Any]] = {}
    for rel in inspect(model).relationships:
        target = rel.mapper.class_
        pk_keys = [inspect(target).get_property_by_column(c).key for c in inspect(target).primary_key]
        label = label_column(target)
        refs[rel.key] = {
            "fields": searchable_columns(target),
            "order_by": ([label] if label else []) + pk_keys,
            "limit": PAGE_SIZE,
        }
    return refs


class PagedAjaxLoader(QueryAjaxModelLoader):
    """sqladmin's loader, plus: empty search lists everything, and results are paged."""

    @classmethod
    def from_loader(cls, loader: QueryAjaxModelLoader) -> "PagedAjaxLoader":
        paged = cls.__new__(cls)
        paged.__dict__.update(loader.__dict__)
        return paged

    async def get_page(self, request: Request, term: str, page: int) -> tuple[list[Any], bool]:
        stmt = select(self.model)
        term = term.strip()
        if term:
            stmt = stmt.filter(or_(*[cast(field, String).ilike(f"%{term}%") for field in self._cached_fields]))
        if self.where is not None:
            stmt = stmt.where(*await self._prepare_where_clauses(request, term))
        if self._cached_fields_order_by:
            stmt = stmt.order_by(*self._cached_fields_order_by)

        stmt = stmt.offset((page - 1) * self.limit).limit(self.limit + 1)  # +1 tells us if there's more
        rows = await self.model_admin._run_query(stmt)
        return rows[: self.limit], len(rows) > self.limit
