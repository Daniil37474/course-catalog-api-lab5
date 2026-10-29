import os
from pathlib import Path
import subprocess
import sys

import psycopg
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

# Never run destructive seed operations against the application's database.
TEST_URL = os.environ.get("TEST_DATABASE_URL")
if not TEST_URL or not make_url(TEST_URL).database.endswith("_test"):
    raise RuntimeError("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
os.environ["DATABASE_URL"] = TEST_URL
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import get_db
from main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def test_engine():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root, check=True)
    url = make_url(TEST_URL)
    with psycopg.connect(host=url.host, port=url.port or 5432, user=url.username,
                         password=url.password, dbname=url.database) as conn:
        conn.execute((root / "seed.sql").read_text(encoding="utf-8"))
    engine = create_engine(TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def session(test_engine):
    with test_engine.connect() as conn:
        outer = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            yield db
        outer.rollback()


@pytest.fixture
def client(session):
    def override_db():
        yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
