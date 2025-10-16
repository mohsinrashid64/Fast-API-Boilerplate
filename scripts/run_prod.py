import os
import subprocess

def run_production():
    cmd = [
        "gunicorn",
        "-k", "uvicorn.workers.UvicornWorker",
        "app.main:app",
        "--bind", "0.0.0.0:8000",
        "--workers", "4"
    ]
    subprocess.run(cmd)

if __name__ == "__main__":
    run_production()
