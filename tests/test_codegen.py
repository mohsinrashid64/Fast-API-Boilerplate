"""Table builder: validation, rendering, the admin endpoint, and a full end-to-end
generation in an isolated copy of the project (the real repo is never written to)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.codegen.generator import GenerationError, render_files, write_files
from app.codegen.spec import ColumnSpec, RelationSpec, SpecError, TableSpec, resolve, suggest_class_name
from app.core.config import PROJECT_ROOT, settings


def _spec(**overrides) -> TableSpec:
    base = dict(
        table_name="sample_gadgets",
        class_name="SampleGadget",
        columns=[ColumnSpec(name="name", type="string", length=80, nullable=False)],
    )
    base.update(overrides)
    return TableSpec(**base)


def _messages(spec: TableSpec) -> str:
    with pytest.raises(SpecError) as exc:
        resolve(spec, PROJECT_ROOT)
    return " | ".join(e["message"] for e in exc.value.errors)


# ---------------------------------------------------------------- validation
@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"table_name": "Bad Name"}, "lowercase"),
        ({"table_name": "products"}, "already exists"),
        ({"table_name": "class"}, "Python keyword"),
        ({"table_name": "admin"}, "reserved"),
        ({"class_name": "sample_gadget"}, "PascalCase"),
        ({"class_name": "User"}, "already exists"),
        ({"columns": []}, "at least one column"),
        ({"columns": [ColumnSpec(name="id", type="integer")]}, "reserved"),
        ({"columns": [ColumnSpec(name="json", type="text")]}, "reserved"),
        ({"columns": [ColumnSpec(name="for", type="text")]}, "Python keyword"),
        ({"columns": [ColumnSpec(name="model_x", type="text")]}, "model_"),
        ({"columns": [ColumnSpec(name="a", type="text"), ColumnSpec(name="a", type="text")]}, "used twice"),
        ({"columns": [ColumnSpec(name="created_at", type="datetime")]}, "added automatically"),
        ({"columns": [ColumnSpec(name="n", type="integer", default="abc")]}, "whole number"),
        ({"columns": [ColumnSpec(name="b", type="boolean", default="maybe")]}, "true or false"),
        ({"columns": [ColumnSpec(name="d", type="date", default="2020-01-01")]}, "'now'"),
        ({"columns": [ColumnSpec(name="j", type="json", default="{bad")]}, "valid JSON"),
        ({"columns": [ColumnSpec(name="s", type="string", length=0)]}, "length"),
        ({"columns": [ColumnSpec(name="m", type="decimal", precision=5, scale=9)]}, "precision"),
        ({"relations": [RelationSpec(column="x_id", target_table="nope")]}, "Unknown table"),
        ({"relations": [RelationSpec(column="product_id", target_table="products", on_delete="SET NULL")]}, "allow empty"),
        ({"owner_scoped": True, "relations": [RelationSpec(column="user_id", target_table="users")]}, "added automatically"),
    ],
)
def test_invalid_specs_are_rejected(overrides, expected):
    assert expected in _messages(_spec(**overrides))


def test_code_injection_attempts_never_reach_the_code():
    import ast

    # Identifiers are validated...
    assert "lowercase" in _messages(_spec(columns=[ColumnSpec(name="x = __import__('os')", type="text")]))
    # ...and default values are rendered as plain string constants.
    evil = '"); import os; os.system("rm -rf /") #\n__import__("os")'
    _, files = render_files(_spec(columns=[ColumnSpec(name="note", type="text", default=evil)]))
    for path, source in files.items():
        tree = ast.parse(source)
        imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
        assert "os" not in imported, path
        calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        assert "__import__" not in calls, path

    model = ast.parse(files["app/models/sample_gadget.py"])
    note = next(n for n in ast.walk(model) if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "note")
    default = next(k.value for k in note.value.keywords if k.arg == "default")
    assert isinstance(default, ast.Constant) and default.value == evil


def test_suggest_class_name():
    assert suggest_class_name("sample_gadgets") == "SampleGadget"
    assert suggest_class_name("order_items") == "OrderItem"
    assert suggest_class_name("boxes") == "Box"
    assert suggest_class_name("address") == "Address"


# ---------------------------------------------------------------- rendering
def test_rendered_files_compile_and_follow_the_layout():
    r, files = render_files(_spec(
        columns=[
            ColumnSpec(name="name", type="string", length=80, nullable=False, unique=True, index=True),
            ColumnSpec(name="price", type="decimal", precision=8, scale=2, default="1.50"),
            ColumnSpec(name="active", type="boolean", nullable=False, default="true"),
            ColumnSpec(name="starts_on", type="date", default="now"),
            ColumnSpec(name="data", type="json", default="{}"),
        ],
        relations=[RelationSpec(column="product_id", target_table="products", nullable=True, on_delete="SET NULL")],
        owner_scoped=True,
    ))
    assert set(files) == {
        "app/models/sample_gadget.py", "app/schemas/sample_gadget.py", "app/crud/sample_gadget_crud.py",
        "app/routes/sample_gadget.py", "tests/test_sample_gadget_api.py",
        next(p for p in files if p.startswith("alembic/versions/") and p.endswith("_create_sample_gadgets.py")),
    }
    for path, source in files.items():
        compile(source, path, "exec")
    assert 'prefix="/sample-gadgets"' in files["app/routes/sample_gadget.py"]
    assert "user_id=current_user.id" in files["app/routes/sample_gadget.py"]
    assert 'Decimal("1.50")' in files["app/models/sample_gadget.py"]


def test_no_tests_file_when_disabled():
    _, files = render_files(_spec(generate_tests=False))
    assert not any(p.startswith("tests/") for p in files)


def test_write_files_never_overwrites(tmp_path):
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "thing.py").write_text("# mine")
    with pytest.raises(GenerationError, match="overwrite"):
        write_files({"app/models/thing.py": "x = 1", "app/routes/thing.py": "y = 2"}, root=tmp_path)
    assert (tmp_path / "app" / "models" / "thing.py").read_text() == "# mine"
    assert not (tmp_path / "app" / "routes" / "thing.py").exists()


# ---------------------------------------------------------------- admin endpoint
async def _admin(client, make_user):
    await make_user("root", "password123", superuser=True)
    assert (await client.post("/admin/login", data={"username": "root", "password": "password123"})).status_code == 302


async def test_preview_endpoint(client, make_user):
    await _admin(client, make_user)
    r = await client.post("/admin/schema", json={"action": "preview", "spec": _spec().model_dump()})
    body = r.json()
    assert body["ok"] and body["api_path"] == "/sample-gadgets"
    assert any(f["path"] == "app/routes/sample_gadget.py" for f in body["files"])

    r = await client.post("/admin/schema", json={"action": "preview", "spec": {**_spec().model_dump(), "table_name": "users"}})
    assert not r.json()["ok"] and r.json()["errors"][0]["field"] == "table_name"

    r = await client.post("/admin/schema", json={"action": "preview", "spec": {"table_name": "x"}})
    assert not r.json()["ok"]  # missing class_name -> readable pydantic error


async def test_builder_is_off_in_production(client, make_user, monkeypatch):
    await _admin(client, make_user)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    r = await client.post("/admin/schema", json={"action": "create", "spec": _spec().model_dump()})
    assert r.status_code == 403
    assert "New table" not in (await client.get("/admin/schema")).text


async def test_schema_json_endpoint(client, make_user):
    await _admin(client, make_user)
    r = await client.get("/admin/schema", params={"format": "json"})
    assert {t["name"] for t in r.json()["tables"]} >= {"users", "products"}


# ---------------------------------------------------------------- end to end (isolated copy)
E2E_SCRIPT = """
import asyncio
from app.codegen.generator import create_table
from app.codegen.spec import ColumnSpec, RelationSpec, TableSpec
spec = TableSpec(
    table_name="sample_gadgets", class_name="SampleGadget", owner_scoped=True,
    columns=[
        ColumnSpec(name="name", type="string", length=120, nullable=False, unique=True),
        ColumnSpec(name="budget", type="decimal", precision=10, scale=2, default="9.50"),
        ColumnSpec(name="is_featured", type="boolean", nullable=False, default="false", index=True),
        ColumnSpec(name="launch_date", type="date", nullable=False, default="now"),
        ColumnSpec(name="meta", type="json"),
        ColumnSpec(name="ratio", type="float"),
        ColumnSpec(name="code", type="string", length=20, unique=True, index=True),
    ],
    relations=[RelationSpec(column="product_id", target_table="products", on_delete="SET NULL", nullable=True)],
)
result = asyncio.run(create_table(spec, apply=True))
assert result["applied"], result
"""

WIRING_SCRIPT = """
from app.admin.views import all_views
from app.codegen.spec import _route_paths
from app.routes import router
paths = _route_paths(router.routes)
assert "/sample-gadgets/" in paths and "/sample-gadgets/{item_id}" in paths, sorted(paths)
assert any(v.model.__name__ == "SampleGadget" for v in all_views())
"""


def test_generate_migrate_and_run_generated_tests(tmp_path):
    work = tmp_path / "project"
    (work / "tests").mkdir(parents=True)
    ignore = shutil.ignore_patterns("__pycache__")
    shutil.copytree(PROJECT_ROOT / "app", work / "app", ignore=ignore)
    shutil.copytree(PROJECT_ROOT / "alembic", work / "alembic", ignore=ignore)
    for name in ("alembic.ini", "pytest.ini"):
        shutil.copy(PROJECT_ROOT / name, work / name)
    for name in ("__init__.py", "conftest.py"):
        shutil.copy(PROJECT_ROOT / "tests" / name, work / "tests" / name)

    env = {
        **os.environ,
        "ENV_FILE": str(work / ".env"),
        "DATABASE_URL": f"sqlite+aiosqlite:///{work / 'app.db'}",
        "PYTHONPATH": str(work),
    }

    def run(*args):
        proc = subprocess.run([sys.executable, *args], cwd=work, env=env, capture_output=True, text=True, timeout=180)
        assert proc.returncode == 0, f"{args}\n{proc.stdout}\n{proc.stderr}"
        return proc.stdout

    run("-c", E2E_SCRIPT)  # generate files + apply the migration
    assert (work / "app" / "models" / "sample_gadget.py").exists()
    run("-m", "alembic", "check")  # generated model and migration agree exactly
    out = run("-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_sample_gadget_api.py")
    assert "3 passed" in out
    run("-c", WIRING_SCRIPT)  # routes + admin page picked up automatically
