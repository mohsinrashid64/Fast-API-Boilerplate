import os
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402


def run_production():
    cmd = [
        "gunicorn",
        "-k", "uvicorn_worker.UvicornWorker",
        "app.main:app",
        "--bind", f"{settings.HOST}:{settings.PORT}",
        "--workers", str(settings.WORKERS),
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    run_production()
