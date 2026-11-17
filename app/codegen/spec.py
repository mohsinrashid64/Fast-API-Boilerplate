"""What the table builder form sends, and the strict validation that turns it into
safe, ready-to-render values. Nothing from the form is ever pasted into generated
code except validated identifiers and `repr()` of parsed literals."""

import json
import keyword
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import inspect

ColumnType = Literal["string", "text", "integer", "big_integer", "float", "decimal", "boolean", "date", "datetime", "json"]
OnDelete = Literal["CASCADE", "SET NULL", "RESTRICT"]

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
CLASS = re.compile(r"^[A-Z][A-Za-z0-9]{0,62}$")

# Names that would clash with SQLAlchemy / Pydantic internals or the generated code itself.
RESERVED_COLUMNS = {
    "id", "metadata", "registry", "query", "self", "cls",
    # Pydantic BaseModel attributes a field must not shadow:
    "dict", "json", "copy", "schema", "fields", "construct", "validate", "parse_obj", "parse_raw",
}
RESERVED_TABLES = {"alembic_version", "admin", "setup", "docs", "redoc", "openapi", "static", "statics"}


class ColumnSpec(BaseModel):
    name: str
    type: ColumnType
    length: int | None = None  # string
    precision: int | None = None  # decimal
    scale: int | None = None  # decimal
    nullable: bool = True
    unique: bool = False
    index: bool = False
    default: str | None = None  # raw text from the form; parsed per type


class RelationSpec(BaseModel):
    column: str  # e.g. "category_id"
    target_table: str
    on_delete: OnDelete = "CASCADE"
    nullable: bool = False


class TableSpec(BaseModel):
    table_name: str
    class_name: str
    columns: list[ColumnSpec] = Field(default_factory=list)
    relations: list[RelationSpec] = Field(default_factory=list)
    timestamps: bool = True
    require_auth: bool = True
    owner_scoped: bool = False
    generate_tests: bool = True


class SpecError(ValueError):
    def __init__(self, errors: list[dict[str, str]]):
        super().__init__("; ".join(e["message"] for e in errors))
        self.errors = errors


# ------------------------------------------------------------------ resolved spec
@dataclass
class Col:
    name: str
    type: str
    sa_type: str  # e.g. "String(120)"  (model)
    sa_migration_type: str  # e.g. "sa.String(length=120)"
    py_type: str  # e.g. "str"
    field_args: str  # e.g. "max_length=120"
    nullable: bool
    unique: bool
    index: bool
    default_expr: str | None  # python expression for the model's `default=`
    schema_default: str | None  # literal for the pydantic schema, or None
    sample: Any
    sample_alt: Any


@dataclass
class Rel:
    column: str
    name: str  # relationship attribute
    target_table: str
    target_class: str
    target_pk: str
    on_delete: str
    nullable: bool
    is_owner: bool = False


@dataclass
class Resolved:
    table_name: str
    class_name: str
    module: str
    url: str
    tag: str
    columns: list[Col]
    relations: list[Rel]
    timestamps: bool
    require_auth: bool
    owner_scoped: bool
    generate_tests: bool
    label_column: str | None
    sa_imports: list[str] = field(default_factory=list)
    needs_decimal: bool = False
    needs_date: bool = False
    needs_datetime: bool = False
    needs_any: bool = False
    test_skip_reason: str | None = None


def py_literal(value: Any) -> str:
    """Python source for a JSON-like value, using double-quoted strings (project style)."""
    if isinstance(value, bool) or value is None:
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(py_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{py_literal(k)}: {py_literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"Unsupported literal: {type(value).__name__}")


def snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def suggest_class_name(table_name: str) -> str:
    """categories -> Category, order_items -> OrderItem (simple English singular)."""
    words = table_name.split("_")
    last = words[-1]
    if last.endswith("ies") and len(last) > 3:
        last = last[:-3] + "y"
    elif last.endswith(("sses", "xes", "ches", "shes")):
        last = last[:-2]
    elif last.endswith("s") and not last.endswith("ss"):
        last = last[:-1]
    words[-1] = last
    return "".join(w.capitalize() for w in words if w)


# ------------------------------------------------------------------ type table
_TYPES = {
    #  type        model type        migration type          python   sample        alt sample
    "text": ("Text", "sa.Text()", "str", "Sample text", "Updated text"),
    "integer": ("Integer", "sa.Integer()", "int", 1, 2),
    "big_integer": ("BigInteger", "sa.BigInteger()", "int", 1, 2),
    "float": ("Float", "sa.Float()", "float", 1.5, 2.5),
    "boolean": ("Boolean", "sa.Boolean()", "bool", True, False),
    "date": ("Date", "sa.Date()", "date", "2026-01-01", "2026-02-01"),
    "datetime": ("DateTime", "sa.DateTime()", "datetime", "2026-01-01T12:00:00", "2026-02-01T12:00:00"),
    "json": ("JSON", "sa.JSON()", "Any", {"key": "value"}, {"key": "updated"}),
}


def _parse_default(col: ColumnSpec, errors: list, where: str) -> tuple[str | None, str | None]:
    """Returns (model default expression, pydantic default literal)."""
    raw = (col.default or "").strip()
    if not raw:
        return None, None

    def bad(msg: str):
        errors.append({"field": f"{where}.default", "message": f"Column '{col.name}': {msg}"})
        return None, None

    t = col.type
    if t in ("string", "text"):
        max_len = col.length if col.length is not None else 255
        if t == "string" and len(raw) > max_len:
            return bad(f"default is longer than {max_len} characters")
        return py_literal(raw), py_literal(raw)
    if t in ("integer", "big_integer"):
        try:
            value = int(raw)
        except ValueError:
            return bad("default must be a whole number")
        return repr(value), repr(value)
    if t == "float":
        try:
            value = float(raw)
        except ValueError:
            return bad("default must be a number")
        if not math.isfinite(value):
            return bad("default must be a finite number")
        return repr(value), repr(value)
    if t == "decimal":
        try:
            value = Decimal(raw)
        except InvalidOperation:
            return bad("default must be a decimal number, e.g. 9.99")
        if not value.is_finite():
            return bad("default must be a finite number")
        return f'Decimal("{value}")', f'Decimal("{value}")'
    if t == "boolean":
        lowered = raw.lower()
        if lowered in ("true", "1", "yes", "on"):
            return "True", "True"
        if lowered in ("false", "0", "no", "off"):
            return "False", "False"
        return bad("default must be true or false")
    if t in ("date", "datetime"):
        if raw.lower() != "now":
            return bad("the only supported default is 'now'")
        return ("func.current_date()" if t == "date" else "func.now()"), None
    if t == "json":
        try:
            value = json.loads(raw)
        except ValueError:
            return bad("default must be valid JSON, e.g. {} or []")
        return f"lambda: {py_literal(value)}", None
    return None, None


def _check_ident(name: str, what: str, where: str, errors: list) -> bool:
    if not IDENT.match(name or ""):
        errors.append({"field": where, "message": f"{what} '{name}' must start with a letter and use only lowercase letters, numbers and _"})
        return False
    if keyword.iskeyword(name):
        errors.append({"field": where, "message": f"{what} '{name}' is a Python keyword"})
        return False
    if name.startswith("model_"):
        errors.append({"field": where, "message": f"{what} '{name}' can't start with 'model_' (reserved by Pydantic)"})
        return False
    return True


def resolve(spec: TableSpec, root: Path) -> Resolved:
    """Validate everything and compute what the templates need. Raises SpecError."""
    import app.models  # noqa: F401  (registers every model on Base)
    from app.database import Base

    errors: list[dict[str, str]] = []
    existing_tables = set(Base.metadata.tables)
    classes = {m.class_.__name__: m for m in Base.registry.mappers}
    tables_to_class = {m.local_table.name: m for m in Base.registry.mappers}

    # ---- names
    table = spec.table_name.strip()
    if _check_ident(table, "Table name", "table_name", errors):
        if table in existing_tables:
            errors.append({"field": "table_name", "message": f"A table named '{table}' already exists"})
        elif table in RESERVED_TABLES:
            errors.append({"field": "table_name", "message": f"'{table}' is reserved"})

    class_name = spec.class_name.strip()
    module = snake_case(class_name)
    if not CLASS.match(class_name or ""):
        errors.append({"field": "class_name", "message": "Model name must be PascalCase, e.g. Category or OrderItem"})
    elif class_name in classes or keyword.iskeyword(class_name):
        errors.append({"field": "class_name", "message": f"A model named '{class_name}' already exists"})
    else:
        for path in _target_paths(root, module, table):
            if path.exists():
                errors.append({"field": "class_name", "message": f"File {path.relative_to(root)} already exists"})

    url = table.replace("_", "-")
    if not errors:
        taken = _route_prefixes()
        if url in taken:
            errors.append({"field": "table_name", "message": f"The API path /{url} is already used"})

    # ---- relations (resolved first so column names can be checked against them)
    rels: list[Rel] = []
    relation_specs = list(spec.relations)
    if spec.owner_scoped:
        if any(r.column == "user_id" for r in relation_specs):
            errors.append({"field": "relations", "message": "'user_id' is added automatically when records belong to a user"})
        relation_specs.insert(0, RelationSpec(column="user_id", target_table="users", on_delete="CASCADE", nullable=False))

    for i, r in enumerate(relation_specs):
        where = f"relations[{i}]"
        is_owner = spec.owner_scoped and i == 0
        if not _check_ident(r.column, "Relation column", f"{where}.column", errors):
            continue
        if r.target_table not in tables_to_class:
            errors.append({"field": f"{where}.target_table", "message": f"Unknown table '{r.target_table}'"})
            continue
        target = tables_to_class[r.target_table]
        pks = list(inspect(target.class_).primary_key)
        if len(pks) != 1:
            errors.append({"field": f"{where}.target_table", "message": f"'{r.target_table}' has a composite primary key; not supported"})
            continue
        if r.on_delete == "SET NULL" and not r.nullable:
            errors.append({"field": f"{where}.on_delete", "message": f"'{r.column}': ON DELETE SET NULL needs the column to allow empty values"})
        name = r.column[:-3] if r.column.endswith("_id") and len(r.column) > 3 else f"{r.column}_ref"
        rels.append(Rel(
            column=r.column, name=name, target_table=r.target_table, target_class=target.class_.__name__,
            target_pk=pks[0].name, on_delete=r.on_delete, nullable=r.nullable, is_owner=is_owner,
        ))

    # ---- columns
    cols: list[Col] = []
    taken_names = {"id"} | ({"created_at", "updated_at"} if spec.timestamps else set())
    for rel in rels:
        for n in (rel.column, rel.name):
            if n in taken_names:
                errors.append({"field": "relations", "message": f"'{n}' is used twice"})
            taken_names.add(n)

    if not spec.columns:
        errors.append({"field": "columns", "message": "Add at least one column"})
    for i, c in enumerate(spec.columns):
        where = f"columns[{i}]"
        if not _check_ident(c.name, "Column", f"{where}.name", errors):
            continue
        if c.name in RESERVED_COLUMNS:
            errors.append({"field": f"{where}.name", "message": f"'{c.name}' is reserved; pick another column name"})
            continue
        if c.name in taken_names:
            errors.append({"field": f"{where}.name", "message": f"'{c.name}' is used twice (or is added automatically)"})
            continue
        taken_names.add(c.name)

        if c.type == "string":
            length = c.length if c.length is not None else 255
            if not 1 <= length <= 10000:
                errors.append({"field": f"{where}.length", "message": f"'{c.name}': length must be 1–10000"})
                continue
            sa_type, mig, py, args = f"String({length})", f"sa.String(length={length})", "str", f"max_length={length}"
            sample, alt = f"sample {c.name}"[:length], f"updated {c.name}"[:length]
        elif c.type == "decimal":
            precision, scale = c.precision or 10, c.scale if c.scale is not None else 2
            if not (1 <= precision <= 38 and 0 <= scale <= precision):
                errors.append({"field": f"{where}.precision", "message": f"'{c.name}': precision 1–38 and scale between 0 and precision"})
                continue
            sa_type = f"Numeric({precision}, {scale})"
            mig = f"sa.Numeric(precision={precision}, scale={scale})"
            py, args = "Decimal", f"max_digits={precision}, decimal_places={scale}"
            sample, alt = "9." + "9" * scale if scale else "9", "1." + "5" * scale if scale else "1"
        else:
            sa_type, mig, py, sample, alt = _TYPES[c.type]
            args = ""

        default_expr, schema_default = _parse_default(c, errors, where)
        cols.append(Col(
            name=c.name, type=c.type, sa_type=sa_type, sa_migration_type=mig, py_type=py, field_args=args,
            nullable=c.nullable, unique=c.unique, index=c.index,
            default_expr=default_expr, schema_default=schema_default, sample=sample, sample_alt=alt,
        ))

    if errors:
        raise SpecError(errors)

    label = next((c.name for c in cols if c.type == "string" and c.name in ("name", "title", "label", "code", "slug")), None)
    used = {c.sa_type.split("(")[0] for c in cols} | {"Column", "Integer"}
    if rels:
        used |= {"ForeignKey"}
    if spec.timestamps:
        used |= {"DateTime", "func"}
    if any(c.default_expr and c.default_expr.startswith("func.") for c in cols):
        used.add("func")

    skip = None
    blocking = [r for r in rels if not r.nullable and not r.is_owner and r.target_table != "users"]
    if blocking:
        skip = f"Needs an existing {blocking[0].target_table} row; extend this test with one."

    return Resolved(
        table_name=table, class_name=class_name, module=module, url=url,
        tag=" ".join(word.capitalize() for word in table.split("_")),
        columns=cols, relations=rels, timestamps=spec.timestamps,
        require_auth=spec.require_auth or spec.owner_scoped, owner_scoped=spec.owner_scoped,
        generate_tests=spec.generate_tests, label_column=label, sa_imports=sorted(used),
        needs_decimal=any(c.py_type == "Decimal" for c in cols),
        needs_date=any(c.py_type == "date" for c in cols),
        needs_datetime=any(c.py_type == "datetime" for c in cols) or spec.timestamps,
        needs_any=any(c.py_type == "Any" for c in cols),
        test_skip_reason=skip,
    )


def _target_paths(root: Path, module: str, table: str) -> list[Path]:
    return [
        root / "app" / "models" / f"{module}.py",
        root / "app" / "schemas" / f"{module}.py",
        root / "app" / "crud" / f"{module}_crud.py",
        root / "app" / "routes" / f"{module}.py",
        root / "tests" / f"test_{module}_api.py",
    ]


def _route_paths(routes, prefix: str = "") -> set[str]:
    """Full paths of all routes, descending into included routers (any FastAPI version)."""
    paths: set[str] = set()
    for route in routes:
        sub = getattr(route, "original_router", None)  # FastAPI >= 0.120 keeps included routers nested
        if sub is not None:
            paths |= _route_paths(sub.routes, prefix)  # its routes already include sub.prefix
            paths.add(prefix + (sub.prefix or ""))
        elif getattr(route, "path", None):
            paths.add(prefix + route.path)
    return paths


def _route_prefixes() -> set[str]:
    from app.routes import router

    segments = {p.strip("/").split("/")[0] for p in _route_paths(router.routes)}
    return {s for s in segments if s} | RESERVED_TABLES
