from pydantic import ValidationError
from sqladmin import BaseView, expose
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.admin.schema import build_schema
from app.codegen.generator import GenerationError, create_table, render_files
from app.codegen.spec import SpecError, TableSpec
from app.core.config import settings
from app.database import AsyncSessionLocal


def codegen_enabled() -> bool:
    """The table builder writes code into the project, so it only exists in development."""
    return not settings.is_production


def _pydantic_errors(exc: ValidationError) -> list[dict[str, str]]:
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err["loc"]]
        field = loc[0] + "".join(f"[{p}]" if p.isdigit() else f".{p}" for p in loc[1:]) if loc else ""
        errors.append({"field": field, "message": f"{field or 'Form'}: {err['msg']}"})
    return errors


class SchemaView(BaseView):
    """Interactive ER diagram generated from the SQLAlchemy models, plus the table builder."""

    name = "Schema"
    icon = "fa-solid fa-diagram-project"

    @expose("/schema", methods=["GET", "POST"], identity="schema")
    async def schema_page(self, request: Request) -> Response:
        if request.method == "POST":
            return await self._table_builder(request)

        # Link each table to its admin list page, when it has one.
        admin_urls = {
            view.model.__table__.name: str(request.url_for("admin:list", identity=view.identity))
            for view in self._admin_ref.views
            if getattr(view, "is_model", False)
        }
        async with AsyncSessionLocal() as session:
            schema = await build_schema(session, admin_urls)

        if request.query_params.get("format") == "json":
            return JSONResponse(schema)

        return await self.templates.TemplateResponse(
            request,
            "erd.html",
            {
                "title": "Database schema",
                "subtitle": "Every table, column and relationship, generated from your SQLAlchemy models.",
                "schema": schema,
                "codegen_enabled": codegen_enabled(),
            },
        )

    async def _table_builder(self, request: Request) -> Response:
        if not codegen_enabled():
            return JSONResponse(
                {"ok": False, "errors": [{"field": "", "message": "The table builder is only available in development."}]},
                status_code=403,
            )
        try:
            body = await request.json()
            spec = TableSpec.model_validate(body.get("spec") or {})
            if body.get("action") == "create":
                result = await create_table(spec, apply=bool(body.get("apply", True)))
                return JSONResponse({"ok": True, **result})
            resolved, files = render_files(spec)
            return JSONResponse(
                {
                    "ok": True,
                    "api_path": f"/{resolved.url}",
                    "files": [{"path": path, "content": source} for path, source in files.items()],
                }
            )
        except ValidationError as exc:
            return JSONResponse({"ok": False, "errors": _pydantic_errors(exc)})
        except SpecError as exc:
            return JSONResponse({"ok": False, "errors": exc.errors})
        except (GenerationError, ValueError) as exc:
            return JSONResponse({"ok": False, "errors": [{"field": "", "message": str(exc)}]})
