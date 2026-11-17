"""Create (or promote) an admin superuser, like Django's `createsuperuser`.

Usage:
    python scripts/create_superuser.py
    python scripts/create_superuser.py --username admin --email admin@gmail.com
    python scripts/create_superuser.py --username admin --email admin@gmail.com --password '...' --no-input
"""

import argparse
import asyncio
import getpass
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, dispose_engine  # noqa: E402
from app.services.bootstrap import create_or_promote_superuser  # noqa: E402


def _prompt(label: str, current: str | None) -> str:
    while not current:
        current = input(f"{label}: ").strip()
    return current


def _prompt_password() -> str:
    while True:
        password = getpass.getpass("Password: ")
        if len(password) < 8:
            print("Password must be at least 8 characters.")
            continue
        if password != getpass.getpass("Password (again): "):
            print("Passwords do not match.")
            continue
        return password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or promote an admin superuser.")
    parser.add_argument("--username")
    parser.add_argument("--email")
    parser.add_argument("--password", help="Avoid on shared machines (shell history); omit to be prompted.")
    parser.add_argument("--no-input", action="store_true", help="Fail instead of prompting for missing values.")
    args = parser.parse_args()

    if not settings.DATABASE_URL:
        parser.exit(1, "DATABASE_URL is not configured. Set it in .env, or start the app and open /setup.\n")

    if args.no_input:
        if not (args.username and args.email and args.password):
            parser.error("--no-input requires --username, --email and --password")
        username, email, password = args.username, args.email, args.password
    else:
        username = _prompt("Username", args.username)
        email = _prompt("Email", args.email)
        password = args.password or _prompt_password()

    if len(password) < 8:
        parser.error("Password must be at least 8 characters.")

    async def run() -> str:
        try:
            async with AsyncSessionLocal() as session:
                user, created = await create_or_promote_superuser(session, username, email, password)
            return f"{'Created superuser' if created else 'Promoted existing user'} '{user.username}' (id={user.id})."
        finally:
            await dispose_engine()

    print(asyncio.run(run()))
    print("Log in at http://<host>:<port>/admin")


if __name__ == "__main__":
    main()
