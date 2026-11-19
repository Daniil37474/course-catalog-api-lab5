"""Apply migrations and load public teaching data into the configured database."""
from pathlib import Path
import subprocess
import sys

import psycopg
from sqlalchemy.engine import make_url
from config import settings
from seed_users import seed_users
from db import SessionLocal

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    url = make_url(settings.database_url)
    if url.database not in {"course_catalog_lab9", "course_catalog_lab9_test"} and url.query.get("options") not in {"-csearch_path=lab9_demo", "-csearch_path=lab9_test"}:
        raise SystemExit("Refusing reset outside the dedicated Lab 9 database/schema")
    print("This replaces teaching catalog data in the configured database/schema.")
    if "--reset-demo" not in sys.argv:
        raise SystemExit("Run python bootstrap.py --reset-demo on a dedicated teaching database.")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)
    url = make_url(settings.database_url)
    with psycopg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False)) as conn:
        conn.execute((root / "seed.sql").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        seed_users(db)
    print("Demo catalog and accounts are ready.")
