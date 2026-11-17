import datetime
import types

from markupsafe import Markup
from sqladmin import ModelView
from sqladmin.formatters import BASE_FORMATTERS
from sqladmin.filters import BooleanFilter, ForeignKeyFilter
from sqlalchemy import Float, inspect, select
from starlette.requests import Request
from wtforms import FloatField, PasswordField
from wtforms.validators import InputRequired, Length, NumberRange, Optional

from app.admin.auth import SESSION_KEY
from app.admin.relations import _SENSITIVE, PagedAjaxLoader, auto_ajax_refs, searchable_columns
from app.database import AsyncSessionLocal
from app.models import OTP, Product, ResetToken, User, UserAuth
from app.utils.hashing import Hash
from app.utils.time import utcnow


def _mask(value: str | None, keep: int = 0) -> str:
    if not value:
        return ""
    return value[:keep] + "•" * min(max(len(value) - keep, 0), 8)


def _pill(text: str, tone: str) -> Markup:
    return Markup('<span class="adm-pill adm-pill-{}">{}</span>').format(tone, text)


def _bool_pill(value: bool) -> Markup:
    return _pill("Yes", "yes") if value else _pill("No", "no")


def _date(value: datetime.datetime) -> Markup:
    return Markup('<span class="adm-date" title="{} UTC">{}</span>').format(
        value.isoformat(sep=" ", timespec="seconds"), value.strftime("%b %d, %Y · %H:%M")
    )


def _expiry(value: datetime.datetime) -> Markup:
    return _date(value) if value > utcnow() else _pill("Expired", "no")


FORMATTERS = {**BASE_FORMATTERS, bool: _bool_pill, datetime.datetime: _date}

# Human-friendly column headers shared by every view (sqladmin falls back to raw field names).
COMMON_LABELS = {
    "id": "ID",
    "user": "User",
    "created_at": "Created",
    "updated_at": "Updated",
    "expires_at": "Expires",
}


class BaseAdminView(ModelView):
    """Shared look & feel for all model views."""

    page_size = 25
    page_size_options = [25, 50, 100]
    description: str = ""  # one-line subtitle shown under the page title
    category = "Tables"  # every model is listed under one "Tables" section in the sidebar
    column_type_formatters = FORMATTERS
    column_type_formatters_detail = FORMATTERS

    def __init__(self) -> None:
        # Every relationship gets a searchable, paged dropdown, so this works for any
        # model added later. A view can still customise one via `form_ajax_refs`.
        self.form_ajax_refs = {**auto_ajax_refs(self.model), **type(self).form_ajax_refs}
        # sqladmin has no form converter for SQLAlchemy 2.1's Float: use a FloatField for every Float column.
        float_cols = {p.key: FloatField for p in inspect(self.model).column_attrs if isinstance(p.columns[0].type, Float)}
        self.form_overrides = {**float_cols, **type(self).form_overrides}
        super().__init__()
        self._form_ajax_refs = {name: PagedAjaxLoader.from_loader(l) for name, l in self._form_ajax_refs.items()}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Merge the common labels underneath each view's own labels.
        cls.column_labels = {**COMMON_LABELS, **getattr(cls, "column_labels", {})}


class UserAdmin(BaseAdminView, model=User):
    name = "User"
    name_plural = "Users"
    description = "Accounts that can sign in to the API. Set passwords and roles here."
    icon = "fa-solid fa-user"

    column_list = [
        User.id, User.username, User.email, User.phone_number,
        User.is_verified, User.is_active, User.is_superuser, User.created_at,
    ]
    column_searchable_list = [User.username, User.email, User.phone_number]
    column_sortable_list = [User.id, User.username, User.email, User.created_at]
    column_default_sort = [(User.id, True)]
    column_filters = [
        BooleanFilter(User.is_verified, title="Verified"),
        BooleanFilter(User.is_active, title="Active"),
        BooleanFilter(User.is_superuser, title="Superuser"),
    ]
    column_details_list = [
        User.id, User.username, User.email, User.phone_number,
        User.is_verified, User.is_active, User.is_superuser,
        User.created_at, User.updated_at, User.products,
    ]
    form_columns = [
        User.username, User.email, User.phone_number,
        User.is_verified, User.is_active, User.is_superuser,
    ]
    column_labels = {
        "username": "Username",
        "email": "Email",
        "phone_number": "Phone",
        "is_verified": "Verified",
        "is_active": "Active",
        "is_superuser": "Superuser",
        "products": "Products",
    }
    column_formatters = {
        User.is_superuser: lambda m, a: _pill("Superuser", "accent") if m.is_superuser else "",
    }

    async def scaffold_form(self, rules=None):
        base_form = await super().scaffold_form(rules)

        class UserForm(base_form):
            password = PasswordField(
                "Password",
                validators=[Optional(), Length(min=8, max=72)],
                description="Sets the user's login password. Leave blank to keep the current one.",
                render_kw={"class": "form-control", "autocomplete": "new-password", "placeholder": "••••••••"},
            )

        return UserForm

    async def on_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        # "password" is not a column: take it out of the data before sqladmin
        # applies the form to the model, and handle it in after_model_change.
        request.state.admin_new_password = data.pop("password", None) or None

        # Don't let an admin lock themselves out.
        if not is_created and model.id == request.session.get(SESSION_KEY):
            if data.get("is_superuser") is False or data.get("is_active") is False:
                raise ValueError("You cannot remove your own superuser or active status.")

        if data.get("email"):
            data["email"] = data["email"].strip().lower()

    async def after_model_change(self, data: dict, model: User, is_created: bool, request: Request) -> None:
        new_password = getattr(request.state, "admin_new_password", None)
        if not new_password:
            return
        async with AsyncSessionLocal() as session:
            user_auth = (
                await session.execute(
                    select(UserAuth).where(UserAuth.user_id == model.id, UserAuth.auth_provider == "password")
                )
            ).scalars().first()
            if user_auth:
                user_auth.password_hash = Hash.hash(new_password)
            else:
                session.add(UserAuth(user_id=model.id, auth_provider="password", password_hash=Hash.hash(new_password)))
            await session.commit()

    async def on_model_delete(self, model: User, request: Request) -> None:
        if model.id == request.session.get(SESSION_KEY):
            raise ValueError("You cannot delete your own account from the admin.")


class UserAuthAdmin(BaseAdminView, model=UserAuth):
    """Login methods per user. Secrets are never displayed; passwords are set from the User page."""

    name = "User Auth"
    name_plural = "User Auth"
    description = "How each user signs in (password, OAuth). Secrets are never shown."
    icon = "fa-solid fa-key"
    can_create = False
    can_edit = False
    can_export = False

    column_list = [UserAuth.id, UserAuth.user, UserAuth.auth_provider, UserAuth.oauth_provider_id, UserAuth.updated_at]
    column_details_exclude_list = [UserAuth.password_hash, UserAuth.oauth_access_token]
    column_sortable_list = [UserAuth.id, UserAuth.auth_provider, UserAuth.updated_at]
    column_searchable_list = [UserAuth.auth_provider, UserAuth.oauth_provider_id]
    column_labels = {"auth_provider": "Provider", "oauth_provider_id": "OAuth ID"}
    column_formatters = {UserAuth.auth_provider: lambda m, a: _pill(m.auth_provider.title(), "accent")}


class ProductAdmin(BaseAdminView, model=Product):
    name = "Product"
    name_plural = "Products"
    description = "Catalog items and stock levels, owned by users."
    icon = "fa-solid fa-box"

    column_list = [Product.id, Product.name, Product.price, Product.stock, Product.user, Product.created_at]
    column_searchable_list = [Product.name, Product.description]
    column_sortable_list = [Product.id, Product.name, Product.price, Product.stock, Product.created_at]
    column_default_sort = [(Product.id, True)]
    column_filters = [ForeignKeyFilter(Product.user_id, User.username, foreign_model=User, title="Owner")]
    column_labels = {"name": "Name", "description": "Description", "price": "Price", "stock": "Stock", "user": "Owner"}
    column_formatters = {
        Product.price: lambda m, a: Markup('<span class="adm-num">{}</span>').format(f"{m.price:,.2f}"),
        Product.stock: lambda m, a: (
            _pill("Out of stock", "danger") if not m.stock
            else _pill(f"{m.stock} left", "warn") if m.stock < 10
            else Markup('<span class="adm-num">{}</span>').format(m.stock)
        ),
    }

    form_columns = [Product.name, Product.description, Product.price, Product.stock, Product.user]
    form_args = {
        "price": {"validators": [InputRequired(), NumberRange(min=0)]},
        "stock": {"validators": [Optional(), NumberRange(min=0)]},
        "user": {"validators": [InputRequired()], "label": "Owner"},
    }


class OTPAdmin(BaseAdminView, model=OTP):
    name = "OTP"
    name_plural = "OTPs"
    description = "One-time verification codes sent at sign-up and login."
    icon = "fa-solid fa-shield-halved"
    can_create = False
    can_edit = False
    can_export = False

    column_list = [OTP.id, OTP.user, OTP.otp_code, OTP.verified, OTP.expires_at, OTP.created_at]
    column_labels = {"otp_code": "Code", "verified": "Used"}
    column_formatters = {
        OTP.otp_code: lambda m, a: Markup('<span class="adm-mono">{}</span>').format(_mask(m.otp_code)),
        OTP.expires_at: lambda m, a: _expiry(m.expires_at),
    }
    column_sortable_list = [OTP.id, OTP.expires_at, OTP.created_at]
    column_default_sort = [(OTP.id, True)]
    column_filters = [BooleanFilter(OTP.verified, title="Used")]


class ResetTokenAdmin(BaseAdminView, model=ResetToken):
    name = "Reset Token"
    name_plural = "Reset Tokens"
    description = "Pending password-reset links. Delete one to revoke it."
    icon = "fa-solid fa-rotate"
    can_create = False
    can_edit = False
    can_export = False

    column_list = [ResetToken.id, ResetToken.user, ResetToken.token, ResetToken.expires_at, ResetToken.created_at]
    column_labels = {"token": "Token"}
    column_formatters = {
        ResetToken.token: lambda m, a: Markup('<span class="adm-mono">{}</span>').format(_mask(m.token, keep=6)),
        ResetToken.expires_at: lambda m, a: _expiry(m.expires_at),
    }
    column_details_exclude_list = [ResetToken.token]
    column_sortable_list = [ResetToken.id, ResetToken.expires_at, ResetToken.created_at]
    column_default_sort = [(ResetToken.id, True)]


ALL_VIEWS = [UserAdmin, UserAuthAdmin, ProductAdmin, OTPAdmin, ResetTokenAdmin]


def _pretty(name: str) -> str:
    """CategoryItem -> Category Item"""
    out = "".join(f" {c}" if c.isupper() and i else c for i, c in enumerate(name))
    return out.strip()


def auto_view(model: type) -> type[BaseAdminView]:
    """A sensible admin page for a model that has no hand-written view
    (e.g. tables created with the Schema page's table builder)."""
    mapper = inspect(model)
    visible = [p.key for p in mapper.column_attrs if not _SENSITIVE.search(p.key)]
    many_to_one = [r.key for r in mapper.relationships if r.direction.name == "MANYTOONE"]
    fk_columns = {c.key for r in mapper.relationships for c in r.local_columns}
    pretty = _pretty(model.__name__)

    attrs = {
        "name": pretty,
        # Plural from the table name ("categories" -> "Categories"), which is already plural.
        "name_plural": " ".join(w.capitalize() for w in mapper.local_table.name.split("_")),
        "icon": "fa-solid fa-table",
        "description": f"Records in the {mapper.local_table.name} table.",
        # Show related records by name instead of raw foreign-key ids.
        "column_list": [k for k in visible if k not in fk_columns] + many_to_one,
        "column_searchable_list": [k for k in searchable_columns(model) if k in visible],
        "column_sortable_list": [k for k in visible if k not in fk_columns],
        "column_default_sort": [(mapper.primary_key[0].key, True)],
        "form_excluded_columns": [k for k in ("created_at", "updated_at") if k in visible],
        # "is_featured" -> "Is featured" (common ones like "id"/"created_at" come from COMMON_LABELS)
        "column_labels": {
            k: k.replace("_", " ").capitalize()
            for k in visible + many_to_one
            if k not in COMMON_LABELS
        },
    }
    return types.new_class(
        f"{model.__name__}AutoAdmin",
        (BaseAdminView,),
        {"model": model},
        lambda ns: ns.update(attrs),
    )


def all_views() -> list[type]:
    """Hand-written views first, then an automatic view for every other model."""
    from app.database import Base

    covered = {view.model for view in ALL_VIEWS}
    auto = [
        auto_view(m.class_)
        for m in sorted(Base.registry.mappers, key=lambda m: m.class_.__name__)
        if m.class_ not in covered
    ]
    return ALL_VIEWS + auto
