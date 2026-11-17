from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parent.parent


def test_migrations_apply_and_match_models(tmp_path):
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.attributes["database_url"] = f"sqlite+aiosqlite:///{tmp_path / 'migrations.db'}"

    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if models and migrations have drifted
    command.downgrade(cfg, "base")
