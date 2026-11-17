"""Introspect the SQLAlchemy models into a plain dict for the ERD page.

Everything comes from `Base.metadata` and the ORM mappers, so the diagram
updates automatically whenever models change.
"""

from typing import Any

from sqlalchemy import ForeignKeyConstraint, Table, UniqueConstraint, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.schema import Column

from app.database import Base, get_engine


def _type_name(column: Column) -> str:
    try:
        return column.type.compile(dialect=get_engine().dialect)
    except Exception:  # some types can't compile for every dialect
        return repr(column.type)


def _default(column: Column) -> str | None:
    default = column.default
    if default is None:
        return None
    arg = getattr(default, "arg", None)
    if callable(arg):
        name = getattr(arg, "__name__", "")
        return f"{name}()" if name and name != "<lambda>" else "python callable"
    return str(arg)


def _server_default(column: Column) -> str | None:
    server_default = column.server_default
    if server_default is None:
        return None
    arg = getattr(server_default, "arg", server_default)
    return str(arg.text if hasattr(arg, "text") else arg)


def _table_info(table: Table, model_name: str | None) -> dict[str, Any]:
    unique_single = {
        next(iter(c.columns)).name
        for c in table.constraints
        if isinstance(c, UniqueConstraint) and len(c.columns) == 1
    }
    indexed = {col.name for idx in table.indexes for col in idx.columns}

    columns = []
    for col in table.columns:
        fks = [
            {"table": fk.column.table.name, "column": fk.column.name, "ondelete": fk.ondelete, "onupdate": fk.onupdate}
            for fk in col.foreign_keys
        ]
        columns.append(
            {
                "name": col.name,
                "type": _type_name(col),
                "primary_key": col.primary_key,
                "nullable": col.nullable,
                "unique": bool(col.unique) or col.name in unique_single,
                "indexed": bool(col.index) or col.name in indexed,
                "autoincrement": col.primary_key and col.autoincrement in (True, "auto"),
                "default": _default(col),
                "server_default": _server_default(col),
                "foreign_keys": fks,
                "comment": col.comment,
            }
        )

    return {
        "name": table.name,
        "model": model_name,
        "comment": table.comment,
        "columns": columns,
        "indexes": [
            {"name": idx.name, "columns": [c.name for c in idx.columns], "unique": bool(idx.unique)}
            for idx in sorted(table.indexes, key=lambda i: i.name or "")
        ],
        "unique_constraints": [
            {"name": c.name, "columns": [col.name for col in c.columns]}
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
        ],
        "relationships": [],
        "row_count": None,
        "admin_url": None,
    }


async def build_schema(session: AsyncSession, admin_urls: dict[str, str] | None = None) -> dict[str, Any]:
    """Return {"tables": [...], "edges": [...]} describing every mapped table."""
    admin_urls = admin_urls or {}
    models_by_table = {m.local_table.name: m for m in Base.registry.mappers}

    tables: dict[str, dict[str, Any]] = {}
    for table in Base.metadata.sorted_tables:
        mapper = models_by_table.get(table.name)
        info = _table_info(table, mapper.class_.__name__ if mapper else None)
        info["admin_url"] = admin_urls.get(table.name)
        info["row_count"] = (await session.execute(select(func.count()).select_from(table))).scalar_one()
        tables[table.name] = info

    # ORM-level relationships (what the Python models expose)
    for table_name, mapper in models_by_table.items():
        for rel in mapper.relationships:
            tables[table_name]["relationships"].append(
                {
                    "name": rel.key,
                    "direction": rel.direction.name,  # ONETOMANY / MANYTOONE / MANYTOMANY
                    "target_model": rel.mapper.class_.__name__,
                    "target_table": rel.mapper.local_table.name,
                    "uselist": bool(rel.uselist),
                    "back_populates": rel.back_populates,
                    "cascade": ", ".join(sorted(rel.cascade)) if rel.cascade else "",
                    "secondary": rel.secondary.name if rel.secondary is not None else None,
                }
            )

    # Database-level foreign keys: one edge per FK constraint (child -> parent)
    edges = []
    for table in Base.metadata.sorted_tables:
        for constraint in table.constraints:
            if not isinstance(constraint, ForeignKeyConstraint):
                continue
            child_cols = [c.name for c in constraint.columns]
            elements = list(constraint.elements)
            parent = elements[0].column.table.name
            parent_cols = [e.column.name for e in elements]
            nullable = all(table.c[c].nullable for c in child_cols)
            unique = len(child_cols) == 1 and any(
                col["name"] == child_cols[0] and (col["unique"] or col["primary_key"])
                for col in tables[table.name]["columns"]
            )
            edges.append(
                {
                    "id": f"{table.name}.{'_'.join(child_cols)}->{parent}",
                    "from_table": table.name,
                    "from_columns": child_cols,
                    "to_table": parent,
                    "to_columns": parent_cols,
                    "ondelete": constraint.ondelete,
                    "onupdate": constraint.onupdate,
                    "optional": nullable,
                    "cardinality": "one-to-one" if unique else "many-to-one",
                }
            )

    return {"tables": list(tables.values()), "edges": edges, "dialect": get_engine().dialect.name}
